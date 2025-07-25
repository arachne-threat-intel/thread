import os

from datetime import datetime
from tests.thread_app_test import ThreadAppTest
from threadcomponents.constants import UID as UID_KEY
from uuid import uuid4


class TestAFBExport(ThreadAppTest):
    """A test suite for checking AFB-export of reports."""

    DB_TEST_FILE = os.path.join("tests", "threadtestafbexport.db")

    async def setUpAsync(self):
        await super().setUpAsync()

        self.report_id, self.report_title = str(uuid4()), "Blitzball: A Guide"
        await self.submit_test_report(
            dict(
                uid=self.report_id,
                title=self.report_title,
                url="lets.blitz",
                date_written="2025-07-25",
            ),
            sentences=[
                ":~$ echo $JECHT_SHOT",
                "For more test data, I need to say some random IP addresses.",
                "2607[:]f8b0[:]400e[:]c01[::]8a",
                "74[.]125[.]199[.]138",
            ],
            attacks_found=[
                [("d99999", "Drain"), ("f32451", "Firaga"), ("s12345", "Yevon")],
                [("d99999", "Drain"), ("f12345", "Fire")],
                [],
                [],
            ],
        )

        self.report_id2, self.report_title2 = str(uuid4()), "Chocobo Racing: A Guide"
        await self.submit_test_report(
            dict(
                uid=self.report_id2,
                title=self.report_title2,
                url="kw.eh",
                date_written="2025-07-25",
            ),
            sentences=[
                "Kweh.",
                "Kweh!?",
            ],
            attacks_found=[
                [("f32451", "Firaga")],
                [],
            ],
            post_confirm_attack=True,
            confirm_attack="f32451",
        )

        await self.confirm_report_attacks()
        await self.save_report_iocs()

    async def confirm_report_attacks(self):
        """Confirms the attacks in the test-report."""
        await self.confirm_report_sentence_attacks(self.report_id, 0, ["d99999", "s12345"])
        await self.confirm_report_sentence_attacks(self.report_id, 1, ["f12345"])

    async def save_report_iocs(self):
        """Saves the IoCs in the test-report."""
        sentence = await self.db.get("report_sentences", equal=dict(report_uid=self.report_id, sen_index=0))
        await self.client.post(
            "/rest",
            json=dict(
                index="add_indicator_of_compromise",
                sentence_id=sentence[0][UID_KEY],
                ioc_text="echo $JECHT_SHOT",
            ),
        )

        for sentence_index in range(2, 4):
            sentence = await self.db.get(
                "report_sentences",
                equal=dict(report_uid=self.report_id, sen_index=sentence_index),
            )
            await self.client.post(
                "/rest",
                json=dict(
                    index="suggest_and_save_ioc",
                    sentence_id=sentence[0][UID_KEY],
                ),
            )

    async def get_export_afb_response(self):
        """Requests the AFB export and returns the response."""
        return await self.client.get("/export/afb/Blitzball%3A%20A%20Guide")

    async def get_attached_afb_as_json(self):
        """Returns the exported AFB as json."""
        response = await self.get_export_afb_response()
        return await response.json()

    @staticmethod
    def get_entries_from_export(exported, id_value):
        """Returns the entries from the exported data given an ID-type."""
        all_objects = exported["objects"]
        filtered_list = []

        for current in all_objects:
            if current["id"] == id_value:
                filtered_list.append(current)

        return filtered_list

    async def trigger_object_by_id_value_test(self, id_value, expected_properties):
        """Given an ID-value in the objects-list, tests the objects for that ID-value are correct."""
        exported = await self.get_attached_afb_as_json()

        retrieved = self.get_entries_from_export(exported, id_value)
        expected_count = len(expected_properties)
        self.assertEqual(len(retrieved), expected_count, f"{expected_count} x {id_value} entries not set.")

        for current in retrieved:
            current_props = dict(current["properties"])

            for key, value in current_props.items():
                if isinstance(value, list):
                    current_props[key] = dict(value)

            self.assertTrue(current_props in expected_properties, f"{id_value} object is an unexpected entry.")

    async def test_response_headers(self):
        """Tests the response headers reflect an attachment."""
        response = await self.get_export_afb_response()

        self.assertEqual(response.content_disposition.type, "attachment", "Response is not an attachment.")
        self.assertEqual(
            response.content_disposition.filename,
            "Blitzball__A_Guide.afb",
            "Attachment's filename is different than expected.",
        )

    async def test_schema(self):
        """Tests the schema is correctly set in the export."""
        exported = await self.get_attached_afb_as_json()
        self.assertEqual(exported["schema"], "attack_flow_v2", "Schema not correctly set.")

    async def test_camera_object(self):
        """Tests the camera-object is correctly set in the export."""
        exported = await self.get_attached_afb_as_json()
        camera = exported["camera"]

        camera_fields = sorted(camera.keys())
        self.assertEqual(camera_fields, ["k", "x", "y"], "Camera-object not correctly set.")

        numbers_provided = all([isinstance(_, int) or isinstance(_, float) for _ in camera.values()])
        self.assertTrue(numbers_provided, "Camera-values are not numbers.")

    async def test_flow_object(self):
        """Tests the flow-object is correctly set in the export."""
        exported = await self.get_attached_afb_as_json()

        flow_objects = self.get_entries_from_export(exported, "flow")
        self.assertEqual(len(flow_objects), 1, "1 x Flow entry not set.")

        properties = dict(flow_objects[0]["properties"])
        self.assertEqual(properties["name"], self.report_title, "Report title not set in export.")

        today = datetime.now()
        exported_date = datetime.strptime(properties["created"], "%Y-%m-%dT%H:%M:%S.%fZ")
        self.assertEqual(today.date(), exported_date.date(), "Created timestamp is not of today.")

        object_list = sorted(flow_objects[0]["objects"])
        declared_ids = []

        for current in exported["objects"]:
            if current["id"] != "flow":
                declared_ids.append(current["instance"])

        self.assertEqual(object_list, sorted(declared_ids), "Objects-list has incorrect IDs.")

    async def test_anchors_key_declared(self):
        """Tests objects from the export have an anchor key."""
        exported = await self.get_attached_afb_as_json()

        for current in exported["objects"]:
            if current["id"] != "flow":
                self.assertTrue("anchors" in current, "Non-flow entry missing 'anchors' key.")

    async def test_layout_object(self):
        """Tests the layout-object is correctly set in the export."""
        exported = await self.get_attached_afb_as_json()

        flow_object = self.get_entries_from_export(exported, "flow")[0]
        object_list = sorted(flow_object["objects"])
        layout = exported["layout"]

        layout_keys = sorted(layout.keys())
        self.assertEqual(layout_keys, object_list, "Layout-object not correctly set.")

        layout_values = [ln for l_coords in layout.values() for ln in l_coords]
        numbers_provided = all([isinstance(_, int) or isinstance(_, float) for _ in layout_values])
        self.assertTrue(numbers_provided, "Layout-values are not numbers.")

    async def test_ipv6_object_declared(self):
        """Tests an IPv6 entry is correctly included in the export."""
        expected = dict(value="2607[:]f8b0[:]400e[:]c01[::]8a")
        await self.trigger_object_by_id_value_test("ipv6_addr", [expected])

    async def test_ipv4_object_declared(self):
        """Tests an IPv4 entry is correctly included in the export."""
        expected = dict(value="74[.]125[.]199[.]138")
        await self.trigger_object_by_id_value_test("ipv4_addr", [expected])

    async def test_process_object_declared(self):
        """Tests a process-entry is correctly included in the export."""
        expected = dict(command_line=":~$ echo $JECHT_SHOT")
        await self.trigger_object_by_id_value_test("process", [expected])

    async def test_malware_object_declared(self):
        """Tests a malware-entry is correctly included in the export."""
        expected = dict(name="Yevon")
        await self.trigger_object_by_id_value_test("malware", [expected])

    async def test_action_objects_declared(self):
        """Tests action-entries are correctly included in the export."""
        expected_1 = dict(
            name="Drain",
            technique_id="T1029",
            technique_ref="d99999",
            ttp=dict(technique="T1029"),
        )
        expected_2 = dict(
            name="Fire",
            technique_id="T1562",
            technique_ref="f12345",
            ttp=dict(technique="T1562"),
        )
        await self.trigger_object_by_id_value_test("action", [expected_1, expected_2])
