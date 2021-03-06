# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2019 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Github Client."""

from datetime import datetime

import pytz
from github3 import login, repository
from lazy_load import lazy_func

from autobot.config_loader import Config


class GitHubAPI:
    """Perform requests for the target repositories."""

    def __init__(self, owner, gh_token):
        """Github client initialization."""
        self.OWNER = owner
        self.GH_CLIENT = login(token=gh_token)

    def fetch_comment_info(self, comment):
        """Fetch information for a comment."""
        return {
            "url": comment.html_url,
            "creation_date": comment.created_at,
            "user": {"name": comment.user.login, "url": comment.user.url},
        }

    def fetch_pr_info(self, pr):
        """Fetch information for a pull request."""
        return {
            "id": pr.number,
            "url": pr.html_url,
            "title": pr.title,
            "creation_date": pr.created_at,
            "description": pr.body,
            "state": pr.state,
            # 'labels': [
            #    {
            #          'name': label.name,
            #          'color': label.color,
            #          'url': label.url
            #    } for label in pr.labels()
            #    ],
            "user": {"name": pr.user.login, "url": pr.user.url},
            "related_issue": pr.issue_url,
        }

    def fetch_issue_info(self, issue):
        """Fetch information for an issue."""
        return {
            "id": issue.number,
            "url": issue.html_url,
            "title": issue.title,
            "creation_date": issue.created_at,
            "description": issue.body,
            "state": issue.state,
            "labels": [
                {"name": label.name, "color": label.color, "url": label.url}
                for label in issue.labels()
            ],
            "user": {"name": issue.user.login, "url": issue.user.url},
        }

    def fetch_repo_info(self, repo):
        """Fetch information for a repository."""
        return {
            "url": repo.clone_url,
            "creation_date": repo.created_at,
            "description": repo.description,
            # 'collaborators': [
            #     {
            #         'name': collaborator.login,
            #         'url': collaborator.url
            #     } for collaborator in repo.collaborators()
            # ],
        }

    def check_mentions(self, m, maintainers):
        """Check if someone in `maintainers` list was mentioned in `m`."""
        res = []
        mentions = list(
            filter(
                lambda login: m.body and (login in [mention[1:] for mention in m.body]),
                maintainers,
            )
        )
        if mentions:
            res.append({"You've been mentioned here!": mentions})
        return res

    def check_mergeable(self, pr, maintainers):
        """Check if pull request `pr` is mergeable."""
        res = []
        if pr.refresh().mergeable:
            res.append({"Merge this!": maintainers})
        return res

    def check_review(self, pr, maintainers):
        """Check if pull request `pr` needs a review."""
        res = []
        requested_reviewers = list(
            filter(
                lambda login: login
                in [reviewer.login for reviewer in pr.requested_reviewers],
                maintainers,
            )
        )
        if requested_reviewers:
            res.append({"Review this!": requested_reviewers})
        return res

    def check_if_connected_with_issue(self, pr, maintainers):
        """Check if pull request `pr` is connected to some issue."""
        res = []
        if pr.issue() is None:
            res.append({"Resolve not connected with issue!": maintainers})
        return res

    def check_close(self, pr, maintainers):
        """Check if pull request `pr` should be closed due to inaction."""
        res = []
        if (datetime.utcnow().replace(tzinfo=pytz.utc) - pr.updated_at).days >= 3 * 30:
            res.append({"Close this!": maintainers})
        return res

    def check_follow_up(self, pr, maintainers):
        """Check if someone should follow up on pull request `pr` due to inaction."""
        res = []
        if ("WIP" in pr.title) and (
            (datetime.utcnow().replace(tzinfo=pytz.utc) - pr.updated_at).days >= 1 * 30
        ):
            res.append({"Follow up on this!": maintainers})
        return res

    def check_labels(self, issue, maintainers):
        """Check issue's `issue` labels."""
        res = []
        if list(filter(lambda label: label.name == "RFC", issue.labels())):
            res.append({"Skip this for now!": maintainers})
        return res

    def check_comments(self, issue, maintainers):
        """Check if a response for an issue's `issue` comment is needed."""
        res = []
        comments = [comment for comment in issue.comments()]
        if comments and comments[-1].user.login not in maintainers:
            res.append({"Follow up on this!": maintainers})
        return res

    comment_filters = [check_mentions]

    pr_filters = [
        check_mergeable,
        check_review,
        check_if_connected_with_issue,
        check_mentions,
        check_close,
        check_follow_up,
    ]

    issue_filters = [check_labels, check_comments, check_mentions]

    def comment_report(self, comment, maintainers):
        """Check a comment for possible actions."""
        res = []
        for f in self.comment_filters:
            res += f(self, comment, maintainers)
        return res

    def pr_report(self, pr, maintainers):
        """Check a pull request for possible actions."""
        res = []
        for f in self.pr_filters:
            res += f(self, pr, maintainers)
        actions = {"review_comments": []}
        for comment in pr.review_comments():
            report = self.comment_report(comment, maintainers)
            actions["review_comments"].append(
                {**{"actions": report}, **self.fetch_comment_info(comment)}
            ) if report else None
        res.append(actions) if actions["review_comments"] else None
        actions = {"issue_comments": []}
        for comment in pr.issue_comments():
            report = self.comment_report(comment, maintainers)
            actions["issue_comments"].append(
                {**{"actions": report}, **self.fetch_comment_info(comment)}
            ) if report else None
        res.append(actions) if actions["issue_comments"] else None
        return res

    def issue_report(self, issue, maintainers):
        """Check an issue for possible actions."""
        res = []
        for f in self.issue_filters:
            res += f(self, issue, maintainers)
        actions = {"comments": []}
        for comment in issue.comments():
            report = self.comment_report(comment, maintainers)
            actions["comments"].append(
                {**{"actions": report}, **self.fetch_comment_info(comment)}
            ) if report else None
        res.append(actions) if actions["comments"] else None
        return res

    def repo_report(self, repo, maintainers):
        """Check a repository for possible actions."""
        res = []
        actions = {"prs": []}
        for pr in repo.pull_requests():
            if pr.state != "open":
                continue
            report = self.pr_report(pr, maintainers)
            actions["prs"].append(
                {**{"actions": report}, **self.fetch_pr_info(pr)}
            ) if report else None
        res.append(actions) if actions["prs"] else None
        actions = {"issues": []}
        for issue in repo.issues():
            if issue.state != "open":
                continue
            report = self.issue_report(issue, maintainers)
            actions["issues"].append(
                {**{"actions": report}, **self.fetch_issue_info(issue)}
            ) if report else None
        res.append(actions) if actions["issues"] else None
        return res

    @lazy_func
    def report(self, repos):
        """Check a repository for possible actions."""
        res = []
        actions = {"repos": []}
        for repo in repos:
            repo_obj = self.GH_CLIENT.repository(self.OWNER, repo)
            report = self.repo_report(repo_obj, repos[repo])
            actions["repos"].append(
                {**{"actions": report}, **self.fetch_repo_info(repo_obj)}
            ) if report else None
        res.append(actions) if actions["repos"] else None
        return res
