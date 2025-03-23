import logging

from threadcomponents.constants import DATETIME_OBJ, REST_IGNORED, REST_SUCCESS, UID
from threadcomponents.enums import ReportStatus
from threadcomponents.helpers.date import to_datetime_obj, pre_save_date_checks
from threadcomponents.managers.base_manager import ReportEntityManager
from threadcomponents.repositories.mapping_repo import MappingRepository


class MappingManager(ReportEntityManager):
    """Manages business logic and validation for Sentence-mappings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mapping_repo = MappingRepository(self.dao)

    async def reject_attack(self, request, criteria):
        """Function to reject a mapping on a sentence."""
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria["sentence_id"], criteria["attack_uid"]
        except (KeyError, TypeError):
            return dict(error="Error rejecting attack.")

        logging.info(f"Rejecting attack {attack_id} for sentence {sen_id}")

        sentence_dict = await self.dao.get("report_sentences", dict(uid=sen_id))
        attack_dict = await self.dao.get("attack_uids", dict(uid=attack_id))

        # Check the method can continue
        checks, report = await self.check_edit_mapping_permission(
            request, sen_id=sen_id, sentence_dict=sentence_dict, attack_id=attack_id, attack_dict=attack_dict
        )
        if checks is not None:
            return checks

        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]["text"])
        sentence_to_insert = self.dao.truncate_str(sentence_to_insert, 800)

        await self.mapping_repo.reject_attack(sen_id, sentence_to_insert, attack_id)

        # As a technique has been rejected, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]["report_uid"], update_if_false=True)
        return REST_SUCCESS

    async def ignore_attack(self, request, criteria):
        """Function to ignore a mapping on a sentence."""
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria["sentence_id"], criteria["attack_uid"]
        except (KeyError, TypeError):
            logging.warning("`sentence_id` or `attack_uid` not found in request data")
            return dict(error="Error rejecting attack.")

        logging.info(f"Ignoring attack {attack_id} for sentence {sen_id}")

        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get("report_sentences", dict(uid=sen_id))
        # Get the attack information for this attack id
        attack_dict = await self.dao.get("attack_uids", dict(uid=attack_id))
        # Check the method can continue
        checks, report = await self.check_edit_mapping_permission(
            request, sen_id=sen_id, sentence_dict=sentence_dict, attack_id=attack_id, attack_dict=attack_dict
        )
        if checks is not None:
            return checks

        await self.mapping_repo.ignore_attack(sen_id, attack_id)

        # As a technique has been rejected, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]["report_uid"], update_if_false=True)
        return REST_SUCCESS

    async def add_attack(self, request, criteria):
        """Function to add a mapping on a sentence."""
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria["sentence_id"], criteria["attack_uid"]
        except (KeyError, TypeError):
            return dict(error="Error adding attack.")

        logging.info(f"Accepting attack {attack_id} for sentence {sen_id}")

        attack_dict = await self.dao.get("attack_uids", dict(uid=attack_id))
        sentence_dict = await self.dao.get("report_sentences", dict(uid=sen_id))

        # Check the method can continue
        checks, report = await self.check_edit_mapping_permission(
            request, sen_id=sen_id, sentence_dict=sentence_dict, attack_id=attack_id, attack_dict=attack_dict
        )
        if checks is not None:
            return checks

        a_name, tid, inactive = attack_dict[0]["name"], attack_dict[0]["tid"], attack_dict[0]["inactive"]
        if inactive:
            return dict(
                error=f"{tid}, '{a_name}' is not in the current Att%ck framework. Please contact us if this is "
                f"incorrect.",
                alert_user=1,
            )

        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]["text"])
        sentence_to_insert = self.dao.truncate_str(sentence_to_insert, 800)

        # Check this sentence + attack combination isn't already in report_sentence_hits
        historic_hits = await self.dao.get("report_sentence_hits", dict(sentence_id=sen_id, attack_uid=attack_id))

        if historic_hits:
            returned_hit = historic_hits[0]
            # If this attack is already confirmed for this sentence, we are not going to do anything further
            if returned_hit["confirmed"]:
                return REST_IGNORED

        await self.mapping_repo.add_attack(
            sentence_dict[0]["report_uid"],
            sen_id,
            sentence_to_insert,
            sentence_dict[0]["found_status"],
            attack_id,
            tid,
            a_name,
            report["start_date_str"],
            historic_hits,
        )

        # As a technique has been added, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]["report_uid"], update_if_false=True)
        return REST_SUCCESS

    async def update_attack_time(self, request, criteria=None):
        """Function to update the time labelled on a mapping or list of mappings."""
        default_error, success = dict(error="Error updating technique times."), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self.check_report_request_data_valid(
            request, criteria, "update-technique-times", [UID, "current_status", "start_date", "end_date"], None
        )
        if error:
            return default_error

        # Check all request parameters
        start_date, end_date = criteria.get("start_date"), criteria.get("end_date")
        mapping_list = criteria.get("mapping_list", [])
        report_id, r_status = report[UID], report["current_status"]
        r_start_date, r_end_date = to_datetime_obj(report["start_date"]), to_datetime_obj(report["end_date"])

        if not start_date:
            return dict(error="Technique Start Date missing.", alert_user=1)

        if (not mapping_list) or (not isinstance(mapping_list, list)):
            return dict(error="No Confirmed Techniques selected.", alert_user=1)

        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error

        # Do date-format and range checks
        start_dict = dict(field="start_date", value=start_date, is_lower=True)
        end_dict = dict(field="end_date", value=end_date, is_upper=True)
        update_data, checks = pre_save_date_checks([start_dict, end_dict], ["start_date"], success)

        if checks:
            return checks

        start_date_conv, end_date_conv = start_dict.get(DATETIME_OBJ), end_dict.get(DATETIME_OBJ)

        mapping_update_count, report_updated = await self.mapping_repo.update_attack_time(
            report_id,
            update_data,
            mapping_list,
            report_start_date=r_start_date,
            report_end_date=r_end_date,
            start_date_object=start_date_conv,
            end_date_object=end_date_conv,
            start_date_str=start_date,
            end_date_str=end_date,
        )

        info = f"{mapping_update_count} of {len(mapping_list)} technique(s) updated."

        if mapping_update_count != len(mapping_list):
            info += " This could be because of report status; unconfirmed technique(s) and/or existing start/end dates."

        report_info, refresh_page = "", False
        if mapping_update_count and report_updated:
            report_info = "Report start/end dates have also been updated."
            refresh_page = True

        current_info = success.pop("info", "")
        info += f" {report_info}" + (("\n\n" + current_info) if current_info else "")
        success.update(
            dict(
                info=info,
                alert_user=1,
                refresh_page=refresh_page,
                updated_attacks=bool(mapping_update_count),
            )
        )

        return success
