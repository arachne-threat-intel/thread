import logging


class ReportRepository:
    # Repository to save various report data to the database
    def __init__(self, dao):
        self.dao = dao

    async def save_reg_techniques(self, report_id, sentence, sentence_index, tech_start_date=None):
        sentence_id = await self.dao.insert_with_backup(
            "report_sentences",
            dict(
                report_uid=report_id,
                text=sentence["text"],
                html=sentence["html"],
                sen_index=sentence_index,
                found_status=self.dao.db_true_val,
            ),
        )
        for technique in sentence["reg_techniques_found"]:
            attack_uid = await self.dao.get("attack_uids", dict(name=technique))
            if not attack_uid:
                attack_uid = await self.dao.get("attack_uids", dict(tid=technique))
                if not attack_uid:
                    attack_uid = await self.dao.get("attack_uids", dict(uid=technique))
            attack_technique = attack_uid[0]["uid"]
            attack_technique_name = "{} (r)".format(attack_uid[0]["name"])
            attack_tid = attack_uid[0]["tid"]
            data = dict(
                sentence_id=sentence_id,
                attack_uid=attack_technique,
                initial_model_match=self.dao.db_true_val,
                attack_technique_name=attack_technique_name,
                report_uid=report_id,
                attack_tid=attack_tid,
            )
            if tech_start_date:
                data.update(dict(start_date=tech_start_date))
            await self.dao.insert_with_backup("report_sentence_hits", data)

    async def save_ml_techniques(self, report_id, sentence, sentence_index, tech_start_date=None):
        sentence_id = await self.dao.insert_with_backup(
            "report_sentences",
            dict(
                report_uid=report_id,
                text=sentence["text"],
                html=sentence["html"],
                sen_index=sentence_index,
                found_status=self.dao.db_true_val,
            ),
        )

        saved_tids = set()
        for technique_tid, technique_name in sentence["ml_techniques_found"]:
            attack_uid = await self.dao.get("attack_uids", dict(tid=technique_tid))

            # If the attack cannot be found via the 'tid' column, try the 'name' column
            if not attack_uid:
                attack_uid = await self.dao.get("attack_uids", dict(name=technique_name))

            # If the attack has still not been retrieved, try searching the similar_words table
            if not attack_uid:
                similar_word = await self.dao.get("similar_words", dict(similar_word=technique_name))
                # If a similar word was found, use its attack_uid to lookup the attack_uids table
                if similar_word and similar_word[0] and similar_word[0]["attack_uid"]:
                    attack_uid = await self.dao.get("attack_uids", dict(uid=similar_word[0]["attack_uid"]))

            # If the attack has still not been retrieved, report to user that this cannot be saved against the sentence
            if not attack_uid:
                logging.warning(
                    " ".join(
                        (
                            "Sentence ID:",
                            str(sentence_id),
                            "ML Technique:",
                            technique_tid,
                            technique_name,
                            "- Technique could not be retrieved from the database; "
                            + "cannot save this technique's association with the sentence.",
                        )
                    )
                )
                # Skip this technique and continue with the next one
                continue

            attack_technique = attack_uid[0]["uid"]
            attack_tech_name = attack_uid[0]["name"]
            attack_tid = attack_uid[0]["tid"]

            if attack_tid in saved_tids:
                continue

            # Allow 'inactive' attacks to be recorded: they will be filtered out when viewing/exporting a report
            data = dict(
                sentence_id=sentence_id,
                attack_uid=attack_technique,
                attack_technique_name=attack_tech_name,
                report_uid=report_id,
                attack_tid=attack_tid,
                initial_model_match=self.dao.db_true_val,
            )

            if tech_start_date:
                data.update(dict(start_date=tech_start_date))

            await self.dao.insert_with_backup("report_sentence_hits", data)
            saved_tids.add(attack_tid)
