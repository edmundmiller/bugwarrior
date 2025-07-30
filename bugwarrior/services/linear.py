import json
import logging
import re
import typing

import requests

from bugwarrior import config
from bugwarrior.services import Client, Issue, Service

log = logging.getLogger(__name__)


class LinearConfig(config.ServiceConfig):
    service: typing.Literal["linear"]
    api_token: str

    host: config.StrippedTrailingSlashUrl = config.StrippedTrailingSlashUrl(
        "https://api.linear.app/graphql", scheme="https", host="api.linear.app"
    )
    import_labels_as_tags: bool = False
    label_template: str = "{{label|replace(' ', '_')}}"
    also_unassigned: config.UnsupportedOption[bool] = False


class LinearIssue(Issue):
    URL = "linearurl"
    TITLE = "lineartitle"
    DESCRIPTION = "lineardescription"
    STATE = "linearstate"
    IDENTIFIER = "linearidentifier"
    TEAM = "linearteam"
    CREATOR = "linearcreator"
    ASSIGNEE = "linearassignee"
    CREATED_AT = "linearcreated"
    UPDATED_AT = "linearupdated"
    CLOSED_AT = "linearclosed"

    UDAS = {
        URL: {"type": "string", "label": "Issue URL"},
        TITLE: {"type": "string", "label": "Issue Title"},
        DESCRIPTION: {"type": "string", "label": "Issue Description"},
        STATE: {"type": "string", "label": "Issue State"},
        IDENTIFIER: {"type": "string", "label": "Linear Identifier"},
        TEAM: {"type": "string", "label": "Project ID"},
        CREATOR: {"type": "string", "label": "Issue Creator"},
        ASSIGNEE: {"type": "string", "label": "Issue Assignee"},
        CREATED_AT: {"type": "date", "label": "Issue Created"},
        UPDATED_AT: {"type": "date", "label": "Issue Updated"},
        CLOSED_AT: {"type": "date", "label": "Issue Closed"},
    }

    UNIQUE_KEY = (URL,)

    def parse_date(self, input):
        '''Parse a date, stripping microseconds'''
        parsed = super().parse_date(input)
        if parsed:
            parsed = parsed.replace(microsecond=0)
        return parsed

    def to_taskwarrior(self):
        description = self.record.get("description")
        created = self.parse_date(self.record.get("createdAt"))
        modified = self.parse_date(self.record.get("updatedAt"))
        closed = self.parse_date(self.record.get("completedAt"))

        # Get a value, defaulting empty results to the given default. Some
        # GraphQL response values, such as for `project`, are either an object
        # or None, rather than being omitted when empty, so this allows chained
        # traversal of such values.
        def get(v, k, default=None):
            r = v.get(k, default)
            if not r:
                return default
            return r

        return {
            "project": re.sub(
                r"[^a-zA-Z0-9]", "_", get(get(self.record, "project", {}), "name", "")
            ).lower() or None,
            "priority": self.config.default_priority,
            "annotations": get(self.extra, "annotations", []),
            "tags": self.get_tags(),
            self.URL: self.record["url"],
            self.TITLE: get(self.record, "title"),
            self.DESCRIPTION: description,
            self.STATE: get(get(self.record, "state", {}), "name"),
            self.IDENTIFIER: get(self.record, "identifier"),
            self.TEAM: get(get(self.record, "team", {}), "name"),
            self.CREATOR: get(get(self.record, "creator", {}), "name"),
            self.ASSIGNEE: get(get(self.record, "assignee", {}), "name"),
            self.CREATED_AT: created,
            self.UPDATED_AT: modified,
            self.CLOSED_AT: closed,
        }

    def get_tags(self):
        labels = [
            label["name"] for label in self.record.get("labels", {}).get("nodes", [])
        ]
        return self.get_tags_from_labels(labels)

    def get_default_description(self):
        return self.build_default_description(
            title=self.record.get("title"),
            url=self.record.get("url"),
            number=self.record.get("identifier"),
            cls="task",
        )


class LinearService(Service, Client):
    ISSUE_CLASS = LinearIssue
    CONFIG_SCHEMA = LinearConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": self.get_password("api_token"), "Content-Type": "application/json"}
        )

        filter = "{}"
        if self.config.only_if_assigned:
            filter = '{assignee: {email: {eq: "%s"}}}' % self.config.only_if_assigned

        self.query = (
            """
            query Issues {
              issues(filter: %s) {
                nodes {
                  url
                  title
                  description
                  assignee {
                    name
                  }
                  creator {name}
                  completedAt
                  updatedAt
                  createdAt
                  project {
                    name
                  }
                  labels {
                    nodes {
                      name
                    }
                  }
                  url
                  state {
                    name
                  }
                  identifier
                  team {
                    name
                  }
                }
              }
            }
            """
            % filter
        )

    @staticmethod
    def get_keyring_service(config):
        return f"linear://{config.host}"

    def issues(self):
        for issue in self.get_issues():
            yield self.get_issue_for_record(issue, {})

    def get_issues(self):
        """
        Make a Linear API request, using the query defined in the constructor.
        """
        response = self.session.post(
            self.config.host, data=json.dumps({"query": self.query})
        )
        res = self.json_response(response)

        if "errors" in res:
            messages = [error.get("message", "Unknown error") for error in res['errors']]
            raise ValueError(messages.join("; "))

        return res.get("data", {}).get("issues", {}).get("nodes", [])
