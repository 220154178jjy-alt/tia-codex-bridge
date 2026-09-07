"""API-shape tests with doubles; these are NOT Siemens SDK or TIA integration tests."""
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from tia_bridge.errors import BridgeError
from tia_bridge.openness import OpennessBackend, OpennessSession


class GenericServices:
    def __init__(self, mapping):
        self.mapping = mapping

    def __getitem__(self, kind):
        return lambda: self.mapping.get(kind)


class Plc:
    pass


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.api = NS(IEngineeringServiceProvider=lambda obj: obj, PlcSoftware=Plc,
                      SoftwareContainer="software", OnlineProvider="online", ICompilable="compiler",
                      FileInfo=lambda path: path, ExportOptions=NS(**{"None": 0}),
                      ImportOptions=NS(**{"None": 0, "Override": 1}))
        self.session = OpennessSession(self.api)
        self.plc = Plc()
        self.plc.Name = "PLC"
        self.online = NS(IsOnline=False)
        self.plc.GetService = GenericServices({"online": self.online})
        self.session.plcs = {"p": self.plc}

    def test_nested_hardware_and_device_groups(self):
        cpu = NS(Name="CPU", DeviceItems=[], GetService=GenericServices({"software": NS(Software=self.plc)}))
        rack = NS(Name="Rack", DeviceItems=[cpu], GetService=GenericServices({}))
        device = NS(Name="Station", DeviceItems=[rack])
        self.session.project = NS(Devices=[], UngroupedDevicesGroup=NS(Devices=[]),
                                  DeviceGroups=[NS(Name="Cell/A", Devices=[device], Groups=[])])
        self.session._index_plcs()
        self.assertEqual(list(self.session.plcs), ["groups/Cell%2FA/Station/Rack/CPU"])

    def test_compile_preserves_nested_errors_and_redacts_addresses(self):
        address = ".".join(["10", "20", "30", "40"])
        nested = NS(State="Error", Description="Cannot read " + address, ErrorCount=2, WarningCount=0, Messages=[])
        top = NS(State="Warning", Description="Group", ErrorCount=2, WarningCount=1, Messages=[nested])
        result = NS(State="Error", ErrorCount=2, WarningCount=1, Messages=[top])
        self.plc.GetService.mapping["compiler"] = NS(Compile=lambda: result)
        output = self.session.compile_plc("p")
        self.assertEqual(output["errors"], 2)
        self.assertEqual(len(output["messages"]), 2)
        self.assertNotIn(address, output["messages"][1]["description"])

    def test_online_and_unverifiable_state_block_writes(self):
        for online in [None, NS(IsOnline=True)]:
            self.plc.GetService.mapping["online"] = online
            with self.assertRaises(BridgeError):
                self.session.compile_plc("p")

    def test_scl_generation_void_return_and_source_retained(self):
        calls = []
        source = NS(GenerateBlocksFromSource=lambda: calls.append("generated"))
        def create(name, path):
            calls.append((name, path))
            return source
        self.plc.ExternalSourceGroup = NS(ExternalSources=NS(CreateFromFile=create))
        result = self.session.import_source("p", "example.scl", True)
        self.assertTrue(result["generated"])
        self.assertEqual(calls, [("example.scl", "example.scl"), "generated"])

    def test_xml_replace_maps_to_explicit_enum(self):
        calls = []
        self.plc.BlockGroup = NS(Blocks=NS(Import=lambda file, option: calls.append(option) or [NS(Name="B")]))
        for replace in [False, True]:
            self.session.import_source("p", "example.xml", replace)
        self.assertEqual(calls, [0, 1])

    def test_timeout_poisons_session_no_duplicate_dispatch(self):
        backend = OpennessBackend("unused", 20, timeout=0.001)
        backend.loaded = True  # No worker means the queued fake operation cannot finish.
        with self.assertRaises(BridgeError) as caught:
            backend.call("save_project")
        self.assertEqual(caught.exception.code, "OPERATION_TIMEOUT")
        self.assertEqual(backend.queue.qsize(), 1)
        with self.assertRaises(BridgeError) as caught:
            backend.call("save_project")
        self.assertEqual(caught.exception.code, "SESSION_UNCERTAIN")
        self.assertEqual(backend.queue.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
