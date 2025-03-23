from threadcomponents.constants import REST_SUCCESS
from threadcomponents.managers.base_manager import ReportEntityManager


class SentenceManager(ReportEntityManager):
    """Manages business logic and validation for Sentences."""

    async def sentence_context(self, request, criteria=None):
        """Function to retrieve all data about a sentence that a user can edit."""
        sen_id = await self.check_and_get_sentence_id(request, request_data=criteria)

        ioc = await self.dao.get("report_sentence_indicators_of_compromise", dict(sentence_id=sen_id))
        ioc = "" if not ioc else ioc[0]["refanged_sentence_text"]

        techniques = await self.data_svc.get_active_sentence_hits(sentence_id=sen_id)

        return dict(techniques=techniques, ioc=ioc)

    async def confirmed_attacks(self, request, criteria=None):
        """Function to retrieve all confirmed attacks of a sentence."""
        sen_id = await self.check_and_get_sentence_id(request, request_data=criteria)
        return await self.data_svc.get_confirmed_attacks_for_sentence(sentence_id=sen_id)

    async def remove_sentence(self, request, criteria=None):
        """Function to delete a sentence."""
        default_error = dict(error="Error removing item.")
        sen_id, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, "delete-sentence"
        )
        if error:
            return error

        # This is most likely a sentence ID sent through, so delete as expected
        await self.dao.delete("report_sentences", dict(uid=sen_id))
        # This could also be an image, so delete from original_html table too
        await self.dao.delete("original_html", dict(uid=sen_id))
        # As a report has been edited, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=report_id, update_if_false=True)
        return REST_SUCCESS
