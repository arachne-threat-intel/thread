from threadcomponents.helpers.date import to_datetime_obj


class MappingRepository:
    """Repository to save various mapping data to the database."""

    def __init__(self, dao):
        self.dao = dao

    async def reject_attack(self, sen_id, sentence_str, attack_id):
        """Executes the database operations to reject a mapping on a sentence."""
        # The list of SQL commands to run in a single transaction
        sql_commands = [
            # Delete any sentence-hits where the model didn't initially guess the attack
            await self.dao.delete(
                "report_sentence_hits",
                dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_false_val),
                return_sql=True,
            ),
            # For sentence-hits where the model did guess the attack, flag as inactive and unconfirmed
            await self.dao.update(
                "report_sentence_hits",
                where=dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_true_val),
                data=dict(active_hit=self.dao.db_false_val, confirmed=self.dao.db_false_val),
                return_sql=True,
            ),
            # This sentence may have previously been added as a true positive or false negative; delete these
            await self.dao.delete("true_positives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete("false_negatives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
        ]

        # Check if the ML model initially predicted this attack, and if it did, then this is a false positive
        model_initially_predicted = len(
            await self.dao.get(
                "report_sentence_hits",
                dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_true_val),
            )
        )
        if model_initially_predicted:
            existing = len(await self.dao.get("false_positives", dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the false positives table if it's not already there
                sql_commands.append(
                    await self.dao.insert_generate_uid(
                        "false_positives",
                        dict(sentence_id=sen_id, attack_uid=attack_id, false_positive=sentence_str),
                        return_sql=True,
                    )
                )

        # Check if this sentence has other attacks mapped to it
        number_of_techniques = await self.dao.get(
            "report_sentence_hits",
            equal=dict(sentence_id=sen_id, active_hit=self.dao.db_true_val),
            not_equal=dict(attack_uid=attack_id),
        )
        # If it doesn't, update the sentence found-status to false
        if len(number_of_techniques) == 0:
            sql_commands.append(
                await self.dao.update(
                    "report_sentences",
                    where=dict(uid=sen_id),
                    data=dict(found_status=self.dao.db_false_val),
                    return_sql=True,
                )
            )

        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)

    async def ignore_attack(self, sen_id, attack_id):
        """Executes the database operations to ignore a mapping on a sentence."""
        # The list of SQL commands to run in a single transaction
        sql_commands = [
            # Delete any sentence-hits where the model didn't initially guess the attack
            await self.dao.delete(
                "report_sentence_hits",
                dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_false_val),
                return_sql=True,
            ),
            # For sentence-hits where the model did guess the attack, flag as inactive and unconfirmed
            await self.dao.update(
                "report_sentence_hits",
                where=dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_true_val),
                data=dict(active_hit=self.dao.db_false_val, confirmed=self.dao.db_false_val),
                return_sql=True,
            ),
            # This sentence may have previously been added as a true/false positive/negative; delete these
            await self.dao.delete("true_positives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete("true_negatives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete("false_positives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete("false_negatives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
        ]
        # Check if this sentence has other attacks mapped to it
        number_of_techniques = await self.dao.get(
            "report_sentence_hits",
            equal=dict(sentence_id=sen_id, active_hit=self.dao.db_true_val),
            not_equal=dict(attack_uid=attack_id),
        )
        # If it doesn't, update the sentence found-status to false
        if len(number_of_techniques) == 0:
            sql_commands.append(
                await self.dao.update(
                    "report_sentences",
                    where=dict(uid=sen_id),
                    data=dict(found_status=self.dao.db_false_val),
                    return_sql=True,
                )
            )

        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)

    async def add_attack(
        self,
        report_id,
        sen_id,
        sentence_str,
        sentence_found_status,
        attack_id,
        tid,
        a_name,
        mapping_start_date,
        mapping_history,
    ):
        """Executes the database operations to add a mapping on a sentence."""
        model_initially_predicted = False
        sql_commands = []

        if mapping_history:
            returned_hit = mapping_history[0]

            # If this attack is already confirmed for this sentence, we are not going to do anything further
            if returned_hit["confirmed"]:
                return

            # Else update the hit as active and confirmed
            sql_commands.append(
                await self.dao.update(
                    "report_sentence_hits",
                    where=dict(sentence_id=sen_id, attack_uid=attack_id),
                    data=dict(active_hit=self.dao.db_true_val, confirmed=self.dao.db_true_val),
                    return_sql=True,
                )
            )

            # Update model_initially_predicted flag using returned history
            model_initially_predicted = returned_hit["initial_model_match"]
        else:
            # Insert new row in the report_sentence_hits database table to indicate a new confirmed technique
            # This is needed to ensure that requests to get all confirmed techniques works correctly
            sql_commands.append(
                await self.dao.insert_generate_uid(
                    "report_sentence_hits",
                    dict(
                        sentence_id=sen_id,
                        attack_uid=attack_id,
                        attack_tid=tid,
                        attack_technique_name=a_name,
                        report_uid=report_id,
                        confirmed=self.dao.db_true_val,
                        start_date=mapping_start_date,
                    ),
                    return_sql=True,
                )
            )

        # As this will now be either a true positive or false negative, ensure it is not a false positive too
        sql_commands.append(
            await self.dao.delete("false_positives", dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True)
        )

        # If the ML model correctly predicted this attack, then it is a true positive
        if model_initially_predicted:
            existing = len(await self.dao.get("true_positives", dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the true positives table if it's not already there
                sql_commands.append(
                    await self.dao.insert_generate_uid(
                        "true_positives",
                        dict(sentence_id=sen_id, attack_uid=attack_id, true_positive=sentence_str),
                        return_sql=True,
                    )
                )
        else:
            # Insert new row in the false_negatives database table as model incorrectly flagged as not an attack
            existing = len(await self.dao.get("false_negatives", dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the false negatives table if it's not already there
                sql_commands.append(
                    await self.dao.insert_generate_uid(
                        "false_negatives",
                        dict(sentence_id=sen_id, attack_uid=attack_id, false_negative=sentence_str),
                        return_sql=True,
                    )
                )

        # If the found_status for the sentence id is set to false when adding a missing technique
        # then update the found_status value to true for the sentence id in the report_sentence table
        if not sentence_found_status:
            sql_commands.append(
                await self.dao.update(
                    "report_sentences",
                    where=dict(uid=sen_id),
                    data=dict(found_status=self.dao.db_true_val),
                    return_sql=True,
                )
            )

        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)

    async def update_attack_time(
        self,
        report_id,
        update_data,
        mapping_list,
        report_start_date=None,
        report_end_date=None,
        start_date_object=None,
        end_date_object=None,
        start_date_str=None,
        end_date_str=None,
    ):
        """Executes the database operations to update the time labelled against mappings."""
        mapping_updates = []
        report_updates = dict()

        for mapping in mapping_list:
            entries = await self.dao.get("report_sentence_hits", dict(uid=mapping))

            # Check if a suitable entry to update or update_data is not already subset of entry (no updates needed)
            if not (
                entries
                and (entries[0].get("report_uid") == report_id)
                and entries[0].get("confirmed")
                and entries[0].get("active_hit")
            ) or (update_data.items() <= entries[0].items()):
                continue

            # Check that if one date in the date range is given, it fits with previously-saved/other date in range
            current_start = to_datetime_obj(entries[0]["start_date"])
            current_end = to_datetime_obj(entries[0]["end_date"])

            invalid_start = (
                start_date_object
                and (not end_date_object)
                and current_end
                and (start_date_object > current_end.replace(tzinfo=None))
            )
            invalid_end = (
                end_date_object
                and (not start_date_object)
                and current_start
                and (end_date_object < current_start.replace(tzinfo=None))
            )
            if invalid_start or invalid_end:
                continue

            mapping_updates.append(
                await self.dao.update(
                    "report_sentence_hits", where=dict(uid=mapping), data=update_data, return_sql=True
                )
            )

        # If there are updates, check if the report start/end dates should be updated
        if mapping_updates:
            all_updates = mapping_updates[:]

            if start_date_object and report_start_date and (start_date_object < report_start_date.replace(tzinfo=None)):
                report_updates.update(dict(start_date=start_date_str))

            if end_date_object and report_end_date and (end_date_object > report_end_date.replace(tzinfo=None)):
                report_updates.update(dict(end_date=end_date_str))

            if report_updates:
                all_updates.append(
                    await self.dao.update("reports", where=dict(uid=report_id), data=report_updates, return_sql=True)
                )

            await self.dao.run_sql_list(sql_list=all_updates)

        return len(mapping_updates), bool(report_updates)
