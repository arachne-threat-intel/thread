from aiohttp import web
from urllib.parse import unquote

from threadcomponents.constants import UID
from threadcomponents.enums import ReportStatus


class ReportEntityManager:
    """Manages business logic and validation for Report-related entities."""

    def __init__(
        self,
        web_svc,
        data_svc,
        dao,
        seen_report_status,
    ):
        self.dao = dao
        self.data_svc = data_svc
        self.web_svc = web_svc
        self.is_local = self.web_svc.is_local
        self.seen_report_status = seen_report_status

    async def check_report_request_data_valid(
        self,
        request,
        criteria,
        action,
        report_variables,
        criteria_variables,
    ):
        """Function that given request data, checks the variables needed for the request are there.
        :return: report, error"""
        try:
            report_title = criteria["report_title"]
        except (KeyError, TypeError):
            return None, True

        for variable in criteria_variables or []:
            try:
                # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
                criteria[variable]
            except (KeyError, TypeError):
                return None, True

        # Get the report data from the provided report title
        try:
            report = await self.data_svc.get_report_by_title(
                report_title=unquote(report_title), add_expiry_bool=(not self.is_local)
            )
        except TypeError:  # Thrown when unquote() receives a non-string type
            return None, True

        # Check we can obtain what we need about the report
        for variable in report_variables or []:
            try:
                report[0][variable]
            except (KeyError, IndexError):  # Thrown if the report title is not in the db or db record is malformed
                return None, True

        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, action, context=dict(report=report[0]))
        return report[0], False

    async def check_report_permission(self, request, report_id="", action="unspecified"):
        """Function to check a request is permitted given an action involving a report ID."""
        # If there is no report ID, the user hasn't supplied something correctly
        if not report_id:
            raise web.HTTPBadRequest()

        # Obtain the report from the db
        report = await self.data_svc.get_report_by_id(report_id=report_id, add_expiry_bool=(not self.is_local))
        try:
            report[0][UID], report[0]["date_written_str"]
        except (KeyError, IndexError):
            # No report exists or db record malformed
            raise web.HTTPBadRequest()

        # Run the checker
        if not self.is_local:
            await self.web_svc.action_allowed(request, action, context=dict(report=report[0]))

        # Checks have passed, return report for further use
        return report[0]

    async def check_report_status(self, report_id="", status=ReportStatus.IN_REVIEW.value, update_if_false=False):
        """Function to check a report is of the given status and updates it if not."""
        # No report ID, no result
        if not report_id:
            return None

        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) == status:
            return True

        # Check the db
        report_dict = await self.dao.get("reports", dict(uid=report_id))
        try:
            db_status = report_dict[0]["current_status"]
        except (KeyError, IndexError):
            # No report exists or db record malformed: return neither True or False
            return None

        # Else a status for this report was retrieved, continue with the method
        # Before returning result, update dictionary for future checks
        self.seen_report_status[report_id] = db_status
        if db_status == status:
            return True  # Report status matches

        # Report status is not a match; finally update db (if requested) and return boolean
        if update_if_false:
            # Update the report status in the db and the dictionary variable for future checks
            await self.dao.update("reports", where=dict(uid=report_id), data=dict(current_status=status))
            self.seen_report_status[report_id] = status
            return True
        else:
            return False  # Report status does not match and we are not updating the db

    async def check_report_status_multiple(self, report_id="", statuses=None):
        """Function to check a report is one of the given statuses."""
        # No report ID or statuses, no result
        if (not report_id) or statuses is None:
            return None

        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) in statuses:
            return True

        # Check the db
        report_dict = await self.dao.get("reports", dict(uid=report_id))
        try:
            db_status = report_dict[0]["current_status"]
        except (KeyError, IndexError):
            # No report exists or db record malformed: return neither True or False
            return None

        # Else a status for this report was retrieved, continue with the method
        # Before returning result, update dictionary for future checks
        self.seen_report_status[report_id] = db_status
        if db_status in statuses:
            return True  # Report status matches
        # Report status is not a match
        return False

    async def check_and_get_sentence_id(self, request, request_data=None):
        """Function to verify request data contains a valid sentence ID and return it."""
        try:
            # Check for malformed request parameters (KeyError) or request_data being None (TypeError)
            sen_id = request_data["sentence_id"]
        except (KeyError, TypeError):
            raise web.HTTPBadRequest()

        report_id = await self.data_svc.get_report_id_from_sentence_id(sentence_id=sen_id)
        if not report_id:
            raise web.HTTPBadRequest()

        # No further checks if local
        if self.is_local:
            return sen_id

        # Check permissions
        await self.check_report_permission(request, report_id=report_id, action="get-sentence")
        return sen_id

    async def check_edit_sentence_permission(
        self,
        request,
        criteria=None,
        default_error=None,
        action="unspecified",
        strict=False,
    ):
        """Function to check a request to edit a sentence is permitted. Returns sentence (ID or data), report ID, error.
        Strict mode: when False, allows matching image-IDs to be checked, else will strictly check sentences only."""
        default_error = default_error or dict(error="Error editing sentence.")

        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            sen_id = criteria["sentence_id"]
        except (KeyError, TypeError):
            return None, None, default_error

        report_id, sentence_data = None, None

        if strict:
            sentences = await self.dao.get("report_sentences", dict(uid=sen_id))
            try:
                sentence_data = sentences[0]
                report_id, _ = sentence_data["report_uid"], sentence_data["text"]
            except (KeyError, TypeError):
                return None, None, default_error

        else:
            report_id = await self.data_svc.get_report_id_from_sentence_id(sentence_id=sen_id)

        # Use this report ID to check permissions, determine its status and if we can continue
        await self.check_report_permission(request, report_id=report_id, action=action)

        if not await self.check_report_status_multiple(
            report_id=report_id, statuses=[ReportStatus.IN_REVIEW.value, ReportStatus.NEEDS_REVIEW.value]
        ):
            return None, None, default_error

        return (sentence_data, report_id, None) if strict else (sen_id, report_id, None)

    async def check_edit_mapping_permission(
        self,
        request,
        sen_id="",
        sentence_dict=None,
        attack_id="",
        attack_dict=None,
    ):
        """Function to check for adding or rejecting attacks, enough sentence and attack data has been given."""
        # Check there is sentence data to access
        try:
            _, _ = sentence_dict[0]["text"], sentence_dict[0]["found_status"]
            report_id = sentence_dict[0]["report_uid"]
        except (KeyError, IndexError):  # sentence error (SE) occurred
            return dict(error="Error. Please quote SE%s when contacting admin." % sen_id, alert_user=1), None

        # Check there is attack data to access
        try:
            attack_dict[0]["name"], attack_dict[0]["tid"]
        except (KeyError, IndexError):  # attack-info error (AE) occurred
            return dict(error="Error. Please quote AE%s when contacting admin." % attack_id, alert_user=1), None

        # Check permissions
        report = await self.check_report_permission(request, report_id=report_id, action="add-reject-attack")

        # Check the report status is acceptable (return a report status error (RSE) if not)
        if not await self.check_report_status_multiple(
            report_id=report_id, statuses=[ReportStatus.IN_REVIEW.value, ReportStatus.NEEDS_REVIEW.value]
        ):
            return dict(error="Error. Please quote RSE%s when contacting admin." % report_id, alert_user=1), None

        return None, report
