import logging

from threadcomponents.constants import DATETIME_OBJ, REST_IGNORED, REST_SUCCESS, UID
from threadcomponents.enums import AssociationWith, ReportStatus
from threadcomponents.helpers.date import to_datetime_obj, pre_save_date_checks, generate_report_expiry
from threadcomponents.managers.base_manager import ReportEntityManager
from threadcomponents.repositories.report_repo import ReportRepository


class ReportManager(ReportEntityManager):
    """Manages business logic and validation for Reports."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_repo = ReportRepository(self.dao)

    def add_report_expiry(self, *args, **kwargs):
        """Function to generate an expiry date from today."""
        if not self.is_local:
            return generate_report_expiry(*args, **kwargs)

    async def save_reg_techniques(self, *args, **kwargs):
        await self.report_repo.save_reg_techniques(*args, **kwargs)

    async def save_ml_techniques(self, *args, **kwargs):
        await self.report_repo.save_ml_techniques(*args, **kwargs)

    async def set_status(self, request, criteria=None):
        """Function to set the status of a report."""
        default_error = dict(error="Error setting status.")
        # Do initial report checks
        report_dict, error = await self.check_report_request_data_valid(
            request, criteria, "set-status", [UID, "current_status", "date_written"], ["set_status"]
        )
        if error:
            return default_error

        new_status = criteria["set_status"]
        report_id, r_status, date_written = report_dict[UID], report_dict["current_status"], report_dict["date_written"]

        # May be refined to allow reverting statuses in future - should use enum to check valid status
        if new_status == ReportStatus.COMPLETED.value:
            # Check there are no unconfirmed attacks
            unchecked = await self.data_svc.get_unconfirmed_undated_attack_count(report_id=report_id)
            if unchecked:
                partial_msg = "%s %s %s" % (
                    "is" if unchecked == 1 else "are",
                    unchecked,
                    "attack" + ("" if unchecked == 1 else "s"),
                )
                return dict(
                    error="There %s unconfirmed or with no start date for this report." % partial_msg, alert_user=1
                )

            # Check the report status is not queued (because queued reports will have 0 unchecked attacks)
            if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
                return default_error
            if not date_written:
                return dict(error="Please set an Article Publication Date for this report.", alert_user=1)

            update_data = dict(current_status=new_status)
            self.add_report_expiry(data=update_data, days=1)
            await self.dao.update("reports", where=dict(uid=report_id), data=update_data)

            self.seen_report_status[report_id] = new_status
            # Before finishing, do any post-complete tasks if necessary
            if not self.is_local:
                report_data = await self.data_svc.export_report_data(report_id=report_id)
                await self.web_svc.on_report_complete(request, report_data)

            return REST_SUCCESS

        else:
            return default_error

    async def rollback_report(self, request, criteria=None):
        """Function to rollback a report to its post-queue state."""
        default_error = dict(error="Error completing rollback of report.")

        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "rollback-report", [UID, "current_status"], None
        )

        if error:
            return default_error

        report_id, r_status = report[UID], report["current_status"]
        # Only mid-review reports can be rollbacked
        if r_status != ReportStatus.IN_REVIEW.value:
            return default_error

        # Proceed with the rollback; first, hide the report from the UI and give it a temp status
        await self.dao.update("reports", where=dict(uid=report_id), data=dict(current_status="HIDDEN"))

        success = await self.data_svc.rollback_report(report_id=report_id)
        if success:
            # Finish by setting the status to 'Needs Review' and removing error (if error was added previously)
            await self.dao.update(
                "reports",
                where=dict(uid=report_id),
                data=dict(current_status=ReportStatus.NEEDS_REVIEW.value, error=self.dao.db_false_val),
            )
            self.seen_report_status[report_id] = ReportStatus.NEEDS_REVIEW.value
            return REST_SUCCESS
        else:
            # If unsuccessful: log this, change report status back to what it was and add error flag
            logging.error("Report %s failed to rollback." % report_id)
            await self.dao.update(
                "reports", where=dict(uid=report_id), data=dict(current_status=r_status, error=self.dao.db_true_val)
            )
            return default_error

    async def delete_report(self, request, criteria=None):
        """Function to delete a report."""
        default_error = dict(error="Error deleting report.")
        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "delete-report", [UID, "current_status", "error"], None
        )
        if error:
            return default_error

        report_id, r_status, r_error = report[UID], report["current_status"], report["error"]

        # Check a queued, error-free report ID hasn't been provided -> this may be mid-analysis
        if (not r_error) and (
            r_status
            not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value, ReportStatus.COMPLETED.value]
        ):
            return default_error

        # Proceed with delete
        await self.dao.delete("reports", dict(uid=report_id))
        return REST_SUCCESS

    async def set_report_categories(self, request, criteria=None):
        """Function to set the categories of a report."""
        default_error, success = dict(error="Error updating report categories."), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "update-report-categories", [UID, "current_status"], None
        )

        if error:
            return default_error

        # Check all request parameters
        categories = criteria.get("categories")
        report_id, r_status = report[UID], report["current_status"]

        if not isinstance(categories, list):
            return REST_IGNORED

        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error

        # Retrieve current report categories
        current = await self.data_svc.get_report_category_keynames(report_id)
        valid_categories = set(self.web_svc.categories_dict.keys()).intersection(categories)

        auto_add = await self.data_svc.get_auto_selected_for_category(valid_categories)
        valid_categories.update(auto_add)

        to_add = valid_categories - set(current)
        to_delete = set(current) - valid_categories

        updates = await self.report_repo.set_report_categories(report_id, to_add, to_delete)

        if updates:
            success.update(dict(info="The report categories have been updated.", alert_user=1))

        return success

    async def set_report_keywords(self, request, criteria=None):
        """Function to set the keywords of a report."""
        default_error, success = dict(error="Error updating aggressors and victims."), REST_SUCCESS.copy()

        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "update-report-keywords", [UID, "current_status"], None
        )

        if error:
            return default_error

        # Check all request parameters
        aggressors = criteria.get("aggressors", dict())
        victims = criteria.get("victims", dict())
        report_id, r_status = report[UID], report["current_status"]

        if not (isinstance(aggressors, dict) and isinstance(victims, dict)):
            return REST_IGNORED

        # Check aggressors and victims are passed as lists within these dictionaries
        for associate_dict in [aggressors, victims]:
            for association_type, associations in associate_dict.items():
                # Check a valid association type has been given (unless we are selecting-all)
                if association_type in ["countries_all", "regions_all", "categories_all"]:
                    continue
                try:
                    AssociationWith(association_type)
                except ValueError:
                    return REST_IGNORED
                # Check the associations for this type are given in a list
                if not isinstance(associations, list):
                    return REST_IGNORED

        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error

        # Retrieve current report aggressors and victims
        current = await self.data_svc.get_report_aggressors_victims(report_id)
        categories = await self.data_svc.get_report_category_keynames(report_id)
        current["victims"]["categories"] = categories or []

        requested_categories = victims.get("category", [])
        auto_add = await self.data_svc.get_auto_selected_for_category(requested_categories)
        if auto_add:
            success.update(refresh_page=True)
            requested_categories += auto_add

        # For each aggressor and victim, have the current-data and request-data ready to compare
        aggressor_assoc = [AssociationWith.CN.value, AssociationWith.RG.value, AssociationWith.GR.value]
        victim_assoc = [
            AssociationWith.CN.value,
            AssociationWith.RG.value,
            AssociationWith.CA.value,
            AssociationWith.GR.value,
        ]
        to_compare = [
            ("aggressor", current["aggressors"], aggressors, False, aggressor_assoc),
            ("victim", current["victims"], victims, True, victim_assoc),
        ]
        # For each aggressor and victim, we know we need to go through countries and groups
        to_process = [
            (
                "report_countries",
                "country",
                "country_codes",
                AssociationWith.CN.value,
                "countries_all",
                self.data_svc.country_dict.keys(),
            ),
            (
                "report_regions",
                "region",
                "region_ids",
                AssociationWith.RG.value,
                "regions_all",
                self.data_svc.region_dict.keys(),
            ),
            (
                "report_categories",
                "category_keyname",
                "categories",
                AssociationWith.CA.value,
                "categories_all",
                self.web_svc.categories_dict.keys(),
            ),
            (
                "report_keywords",
                "keyword",
                "groups",
                AssociationWith.GR.value,
                None,
                self.web_svc.keyword_dropdown_list,
            ),
        ]

        updates = await self.report_repo.set_report_keywords(report_id, to_compare, to_process)

        if updates:
            success.update(dict(info="The report aggressors and victims have been updated.", alert_user=1))

        return success

    async def update_report_dates(self, request, criteria=None):
        """Function to update the date-fields of a report."""
        default_error, success = dict(error="Error updating report dates."), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "update-report-dates", [UID, "current_status", "date_written"], None
        )
        if error:
            return default_error

        date_of, start_date, end_date = criteria.get("date_of"), criteria.get("start_date"), criteria.get("end_date")

        # We only want to process booleans sent for these parameters
        same_dates, apply_to_all = criteria.get("same_dates") is True, criteria.get("apply_to_all") is True
        report_id, r_status, r_written = report[UID], report["current_status"], report["date_written"]
        r_start, r_end = to_datetime_obj(report["start_date"]), to_datetime_obj(report["end_date"])

        # Check a queued or completed report ID hasn't been provided
        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error

        # Has a date-written not been provided if the report entry in db is lacking one?
        if (not r_written) and not date_of:
            return dict(error="Article Publication Date missing.", alert_user=1)

        # Do date-format and range checks
        start_dict = dict(field="start_date", value=start_date, is_lower=True)
        end_dict = dict(field="end_date", value=end_date, is_upper=True)

        dates = [dict(field="date_written", value=date_of), start_dict, end_dict]
        update_data, checks = pre_save_date_checks(dates, ["date_written"], success)

        if checks:
            return checks

        # Carry out further checks and final data tidy up before updating the database
        start_date_conv, end_date_conv = start_dict.get(DATETIME_OBJ), end_dict.get(DATETIME_OBJ)
        if (start_date_conv and end_date_conv) and same_dates and (end_date_conv != start_date_conv):
            return dict(error="Specified same dates but different dates provided.", alert_user=1)

        # Check that if one date in the date range is given, it fits with previously-saved/other date in range
        far_start_date = (
            start_date_conv and (not end_date_conv) and r_end and (start_date_conv > r_end.replace(tzinfo=None))
        )
        near_end_date = (
            end_date_conv and (not start_date_conv) and r_start and (end_date_conv < r_start.replace(tzinfo=None))
        )
        if far_start_date or near_end_date:
            return dict(
                error="The start/end dates do not follow the order of the existing start/end dates.", alert_user=1
            )

        # Are there any techniques that have start/end dates that don't fit with these new report dates?
        if (not apply_to_all) and (start_date or end_date):
            out_of_bounds = await self.report_repo.get_report_dates_out_of_range(report_id, start_date, end_date)

            if out_of_bounds:
                number = len(out_of_bounds)
                error_msg = (
                    f"{number} confirmed technique"
                    f"{' has' if number == 1 else 's have'} "
                    "start/end dates outside specified range."
                )
                return dict(error=error_msg, alert_user=1)

        if same_dates and start_date_conv:
            update_data["end_date"] = start_date

        # Update the database if there were values to update with; inform user of any which were ignored
        if update_data:
            await self.report_repo.set_report_dates(report_id, update_data, apply_to_all)

        if not success.get("info"):  # the success response hasn't already been updated with info
            success.update(dict(info="The report dates have been updated.", alert_user=1))

        return success
