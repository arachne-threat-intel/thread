import re

from threadcomponents.constants import REST_IGNORED, REST_SUCCESS, UID
from threadcomponents.helpers.ip_address import check_if_public_ip
from threadcomponents.managers.base_manager import ReportEntityManager


class IoCManager(ReportEntityManager):
    """Manages business logic and validation for Sentence-IoCs."""

    async def suggest_and_save_ioc(self, request, criteria=None):
        """Function to suggest and save a sentence's indicator-of-compromise text."""
        suggested_ioc_resp = (await self.suggest_ioc(request, criteria=criteria)) or ""
        final_response = suggested_ioc_resp
        ioc_text = None

        if isinstance(suggested_ioc_resp, str):
            ioc_text = criteria["ioc_text"] = suggested_ioc_resp
            final_response = await self.update_ioc(request, criteria=criteria)

        if isinstance(final_response, dict) and final_response.get("success") and ioc_text:
            final_response["ioc_text"] = ioc_text

        return final_response

    async def suggest_ioc(self, request, criteria=None):
        """Function to predict a sentence as an indicator of compromise."""
        default_error = dict(error="Error predicting IoC.")
        sentence_data, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, "predict-ioc", strict=True
        )

        if error:
            return error

        text = sentence_data["text"]
        if not text:
            return REST_IGNORED

        cleaned_ioc_text = self.__refang(text)
        is_public_ip, cleaned_ioc_text = check_if_public_ip(cleaned_ioc_text, clean=True)
        return cleaned_ioc_text

    async def update_ioc(self, request, criteria=None, adding=False, deleting=False):
        """Function to update a sentence as an indicator of compromise."""
        if adding and deleting:
            raise ValueError("Parameters for adding and deleting are both set to True.")
        default_error, success = dict(error="Error updating IoC."), REST_SUCCESS.copy()
        sentence_data, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, "update-ioc", strict=True
        )
        if error:
            return error

        table = "report_sentence_indicators_of_compromise"
        db_query = dict(report_id=report_id, sentence_id=sentence_data[UID])

        if deleting:
            await self.dao.delete(table, db_query)
            success.update(dict(info="The selected sentence is no longer flagged as an IoC.", alert_user=1))
            return success

        text = criteria.get("ioc_text", "").strip()
        existing = await self.dao.get(table, db_query)
        if (adding and existing) or (not text):  # prevent duplicates
            return default_error
        # Don't automatically clean IoC for the user
        is_public_ip, cleaned_ip = check_if_public_ip(text, clean=False)

        if is_public_ip is False:  # avoid `if not` because None means not an IP address
            error_msg = (
                "This appears to be a link-local, multicast, or private IP address. "
                "This cannot be flagged as an IoC. (Contact us if this is incorrect!)"
            )
            return dict(error=error_msg, alert_user=1)

        if existing and not adding:
            if existing[0]["refanged_sentence_text"] == text:
                return REST_IGNORED
            await self.dao.update(table, where=db_query, data=dict(refanged_sentence_text=text))
            success.update(dict(info="This sentence-IoC text has been updated.", alert_user=1))
        else:
            await self.dao.insert_generate_uid(table, dict(**db_query, refanged_sentence_text=text))
            success.update(dict(info="The selected sentence has been flagged as an IoC.", alert_user=1))

        return success

    def __refang(self, ioc_text):
        """Function to remove artifacts from common defangs."""
        if not ioc_text:
            return

        ioc_text = ioc_text.replace("\n", "").replace(" ", "")
        # Make some characters consistent
        replace_periods = "[%s]+" % re.escape("".join(self.web_svc.PERIODS))
        ioc_text = re.sub(replace_periods, ".", ioc_text)
        # 2 x single quotes in the regex below adds the single quote to the character set; do a separate remove
        remove_quotes = "[%s]+" % re.escape("".join(set(self.web_svc.QUOTES) - {"''"}))
        ioc_text = re.sub(remove_quotes, "", ioc_text)
        ioc_text = re.sub("(%s)+" % re.escape("''"), "", ioc_text)

        ioc_text = (
            ioc_text.replace(",", ".")
            .replace("[dot]", ".")
            .replace("(dot)", ".")
            .replace("[.]", ".")
            .replace("(.)", ".")
            .replace("[at]", "@")
            .replace("(at)", "@")
            .replace("[@]", "@")
            .replace("(@)", "@")
            .replace("[:]", ":")
            .replace("(:)", ":")
            .replace("(", "")
            .replace(")", "")
            .replace("[", "")
            .replace("]", "")
        )

        # Replacements to make at the beginning and end of the string
        replace_start = ["*"] + self.web_svc.BULLET_POINTS + self.web_svc.HYPHENS
        replace_end = ["."] + self.web_svc.HYPHENS
        replace_start_pattern = "^[%s]+" % re.escape("".join(replace_start))
        replace_end_pattern = "[%s]+$" % re.escape("".join(replace_end))

        ioc_text = re.sub(replace_start_pattern, "", ioc_text)
        # Special case: not removing but replacing leading 'hxxp'
        if ioc_text.startswith("hxxp"):
            ioc_text = ioc_text.replace("hxxp", "http", 1)
        ioc_text = re.sub(replace_end_pattern, "", ioc_text)

        return ioc_text
