import logging


class ReportRepository:
    """Repository to save / retrieve various report data to / from the database."""

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

    async def set_report_categories(self, report_id, to_add, to_delete):
        """Executes the database operations to set the categories of a report."""
        sql_list = []

        for category in to_add:
            sql_list.append(
                await self.dao.insert_generate_uid(
                    "report_categories", dict(report_uid=report_id, category_keyname=category), return_sql=True
                )
            )

        for category in to_delete:
            sql_list.append(
                await self.dao.delete(
                    "report_categories", dict(report_uid=report_id, category_keyname=category), return_sql=True
                )
            )

        await self.dao.run_sql_list(sql_list=sql_list)
        return bool(sql_list)

    async def set_report_keywords(self, report_id, to_compare, to_process):
        """Executes the database operations to set the keywords of a report."""
        sql_list = []

        # Comparing current-data and request-data dictionaries: loop once to see if we're selecting all
        for assoc_type, current_assoc_dict, request_assoc_dict, allow_select_all, allowed_assoc_types in to_compare:
            if not allow_select_all:
                continue

            # Given the table names/columns, keys to use in the dictionaries ('*_k'), and list of valid values...
            for table_name, table_col, current_k, request_k, sel_all_k, valid_list in to_process:
                if not sel_all_k:
                    continue

                currently_is_all = current_assoc_dict[sel_all_k]
                requesting_is_all = request_assoc_dict.get(sel_all_k)

                if requesting_is_all:
                    # If we are requesting all, ignore any specified values in the list
                    request_assoc_dict[request_k] = []

                    if not currently_is_all:
                        # Requesting all when not currently-all: add an entry in the select-all table for this report
                        db_entry = dict(report_uid=report_id, association_type=assoc_type, association_with=request_k)
                        sql_list.append(
                            await self.dao.insert_generate_uid("report_all_assoc", db_entry, return_sql=True)
                        )

                if currently_is_all:
                    # Currently all when not requesting all and values specified...
                    if (not requesting_is_all) and request_assoc_dict.get(request_k):
                        # ...delete entry in the select-all table for this report
                        db_entry = dict(report_uid=report_id, association_type=assoc_type, association_with=request_k)
                        sql_list.append(await self.dao.delete("report_all_assoc", db_entry, return_sql=True))

        # Loop twice to determine which association db entries need to be updated
        for assoc_type, current_assoc_dict, request_assoc_dict, allow_select_all, allowed_assoc_types in to_compare:
            for table_name, table_col, current_k, request_k, sel_all_k, valid_list in to_process:
                if request_k not in allowed_assoc_types:
                    continue

                # From the dictionary and using its relevant key, extract the current and requested data as sets
                current_set = set(current_assoc_dict[current_k])
                requested_set = set(request_assoc_dict.get(request_k, []))

                # Using the valid list of values, determine which of the requested values are valid
                valid_request_values = set(valid_list).intersection(requested_set)

                # Finally determine what values are being added and deleted
                to_add = valid_request_values - set(current_set)
                to_delete = set(current_set) - valid_request_values

                # Build the SQL query for this aggressor/victim country/group
                db_entry = dict(report_uid=report_id, association_type=assoc_type)
                for assoc_val in to_add:
                    temp = db_entry.copy()
                    temp[table_col] = assoc_val
                    sql_list.append(await self.dao.insert_generate_uid(table_name, temp, return_sql=True))

                # Check if there are deletions and current_set = to_delete; if so, no point doing individual deletes
                if (current_set == to_delete) and bool(to_delete) and not bool(to_add):
                    sql_list.append(await self.dao.delete(table_name, db_entry, return_sql=True))
                else:
                    for assoc_val in to_delete:
                        temp = db_entry.copy()
                        temp[table_col] = assoc_val
                        sql_list.append(await self.dao.delete(table_name, temp, return_sql=True))

        await self.dao.run_sql_list(sql_list=sql_list)
        return bool(sql_list)

    async def get_report_dates_out_of_range(self, report_id, start_date, end_date):
        """Returns report-mappings where their dates are outside a given date range."""
        start_date_lt = f"start_date < {self.dao.db_qparam}"
        start_date_gt = f"start_date > {self.dao.db_qparam}"
        end_date_lt = f"end_date < {self.dao.db_qparam}"
        end_date_gt = f"end_date > {self.dao.db_qparam}"

        if start_date and end_date:
            # Is there a start-date less-than the given start-date; an end-date greater-than the given end-date, etc.
            date_query = f"({start_date_lt} OR {end_date_gt} OR {start_date_gt} OR {end_date_lt})"
            date_params = [start_date, end_date, end_date, start_date]

        elif start_date:
            date_query = f"({start_date_lt} OR {end_date_lt})"
            date_params = [start_date, start_date]

        elif end_date:
            date_query = f"({end_date_gt} OR {start_date_gt})"
            date_params = [end_date, end_date]

        else:
            return

        bounds_query = (
            f"SELECT * FROM report_sentence_hits WHERE {date_query} AND report_uid = "
            f"{self.dao.db_qparam} AND confirmed = {self.dao.db_true_val}"
        )

        return await self.dao.raw_select(bounds_query, parameters=tuple(date_params + [report_id]))

    async def set_report_dates(self, report_id, update_data, apply_to_mappings):
        """Executes the database operations to set the dates of a report."""
        sql_list = [
            await self.dao.update("reports", where=dict(uid=report_id), data=update_data, return_sql=True),
        ]

        if apply_to_mappings:  # if we're applying the report date range to all techniques...
            techs_update_data = dict()

            if "start_date" in update_data:
                techs_update_data.update(dict(start_date=update_data.get("start_date")))

            if "end_date" in update_data:
                techs_update_data.update(dict(end_date=update_data.get("end_date")))

            if techs_update_data:
                # WHERE clause can be just matching this report ID; narrowing this to unconfirmed techs might cause
                # issues when they are later confirmed and have old/different date ranges
                sql_list.append(
                    await self.dao.update(
                        "report_sentence_hits",
                        where=dict(report_uid=report_id),
                        data=techs_update_data,
                        return_sql=True,
                    )
                )

        await self.dao.run_sql_list(sql_list=sql_list)
