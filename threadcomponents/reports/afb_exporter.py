from datetime import datetime
from ipaddress import ip_address, IPv4Address, IPv6Address
from threadcomponents.constants import TTP, IOC
from uuid import uuid4

START_X = 0
START_Y = -2000
TILE_SHIFT = 400
TILES_PER_ROW = 3

NAME_CHAR_LIMIT = 60


class AFBExporter:
    """A class to export report mappings in an AFB format."""

    def __init__(self, report_title, report_data):
        self.report_title = report_title
        self.report_data = report_data
        self.reset()

    def reset(self):
        self.exported = {
            "schema": "attack_flow_v2",
        }
        self.objects = []
        self.current_ids = set()

        self.layout = {}
        self.current_x = START_X
        self.current_y = START_Y

        self.name = ""
        self.description = None
        self.errors = []

    def export(self):
        """Executes the export."""
        self.reset()
        self._set_name_and_description()
        self._build_objects_list()
        self._add_layout_object()
        self._add_camera_object()
        return self.exported

    def _build_objects_list(self):
        """Build the objects list to be included in the exported data."""
        for data in self.report_data:
            data_type = data.get("type")
            mapping_key = data.get("tid") or "IOC"
            text_truncated = data.get("text", "").replace("\n", "")[:10]
            entry_str = f"{mapping_key} - {text_truncated}"

            tile_id = self._generate_tile_id(entry_str)
            if not tile_id:
                continue

            added = False

            if data_type == IOC:
                added = self._add_ioc_object(tile_id, data)

            elif data_type == TTP:
                if mapping_key.startswith("T"):
                    added = self._add_ttp_object(tile_id, data)

                elif mapping_key.startswith("S"):
                    added = self._add_malware_object(tile_id, data)

            if added:
                self._add_tile_to_layout(tile_id)

        self._finalise_objects_list()

    def _set_name_and_description(self):
        """Sets the name and description to be exported."""
        if len(self.report_title) >= NAME_CHAR_LIMIT:
            self.name = f"{self.report_title[: NAME_CHAR_LIMIT - 1]}-"
            self.description = self.report_title

        else:
            self.name = self.report_title

    def _finalise_description(self):
        """Finalises the description to include any errors that occurred during export."""
        error_str = "\n".join(self.errors)

        if error_str:
            self.description = f"{self.description}\n\n" if self.description else ""
            self.description += error_str

    def _finalise_objects_list(self):
        """Finalises the objects-list to be exported."""
        flow_entry = self._generate_flow_object()
        self.exported["objects"] = [flow_entry] + self.objects

    def _add_layout_object(self):
        """Adds the layout-entry to the exported data."""
        self.exported["layout"] = self.layout

    def _add_camera_object(self):
        """Adds the camera-entry to the exported data."""
        self.exported["camera"] = {
            "x": START_X + TILE_SHIFT,
            "y": START_Y + TILE_SHIFT,
            "k": 0.5,
        }

    def _generate_flow_object(self):
        """Generates and returns the flow-entry to be added to the exported data."""
        self._finalise_description()

        return {
            "id": "flow",
            "properties": [
                ["name", self.name],
                ["description", self.description],
                [
                    "author",
                    [
                        ["name", None],
                        ["identity_class", "individual"],
                    ],
                ],
                ["scope", "attack-tree"],
                ["created", datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")],
            ],
            "objects": list(self.current_ids),
        }

    def _add_ioc_object(self, tile_id, data):
        """Adds the IoC-entry to the objects-list."""
        try:
            return self._add_ip_object(tile_id, data)

        except ValueError:
            return self._add_command_line_object(tile_id, data)

    def _add_ip_object(self, tile_id, data):
        """Adds the IP-entry to the objects-list."""
        ioc_cleaned_text = data.get("refanged_text", "")
        ioc_text = data.get("text", "")

        ip_obj = ip_address(ioc_cleaned_text)
        tile_type = None

        if isinstance(ip_obj, IPv4Address):
            tile_type = "ipv4_addr"
        elif isinstance(ip_obj, IPv6Address):
            tile_type = "ipv6_addr"

        if tile_type:
            self._add_object(
                tile_id,
                tile_type,
                properties=[
                    ["value", ioc_text],
                ],
            )
            return True

    def _add_command_line_object(self, tile_id, data):
        """Adds the command-line-entry to the objects-list."""
        executed = data.get("text", "")

        self._add_object(
            tile_id,
            "process",
            properties=[
                ["command_line", executed],
            ],
        )
        return True

    def _add_ttp_object(self, tile_id, data):
        """Adds the TTP-entry to the objects-list."""
        tech_name = data.get("name")
        tech_tid = data.get("tid")
        tech_uid = data.get("attack_uid")

        self._add_object(
            tile_id,
            "action",
            properties=[
                ["name", tech_name],
                ["technique_id", tech_tid],
                ["technique_ref", tech_uid],
                [
                    "ttp",
                    [
                        ["technique", tech_tid],
                    ],
                ],
            ],
        )

        return True

    def _add_malware_object(self, tile_id, data):
        """Adds the malware-entry to the objects-list."""
        malware_name = data.get("name")

        self._add_object(
            tile_id,
            "malware",
            properties=[
                ["name", malware_name],
            ],
        )
        return True

    def _add_object(self, tile_id, id_val, properties=None):
        """Adds an-entry to the objects-list."""
        properties = properties or []

        self.objects.append(
            {
                "id": id_val,
                "instance": tile_id,
                "properties": properties,
                "anchors": {},
            }
        )

    def _add_tile_to_layout(self, tile_id):
        """Updates the layout object to place the given tile_id."""
        self.layout[tile_id] = [self.current_x, self.current_y]
        self._update_current_position()

    def _update_current_position(self):
        """Updates the current position in the layout."""
        self.current_x += TILE_SHIFT

        if self.current_x > (TILE_SHIFT * TILES_PER_ROW):
            self.current_x = 0
            self.current_y += TILE_SHIFT

    def _generate_tile_id(self, log_missing):
        """Generates and returns a new ID."""
        for _ in range(5):
            new_id = str(uuid4())

            if new_id not in self.current_ids:
                self.current_ids.add(new_id)
                return new_id

        self.errors.append(f"Missing {log_missing}")
