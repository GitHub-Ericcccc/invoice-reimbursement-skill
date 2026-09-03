from __future__ import annotations

import re
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET = REPO_ROOT / "skill" / "invoice-reimbursement" / "assets" / "报销表模板.xlsx"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def cell_values(archive: zipfile.ZipFile) -> dict[str, object]:
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.findall(f"{{{MAIN_NS}}}si"):
            shared.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))

    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    values: dict[str, object] = {}
    for cell in sheet.iter(f"{{{MAIN_NS}}}c"):
        address = cell.attrib["r"]
        value = cell.find(f"{{{MAIN_NS}}}v")
        inline = cell.find(f"{{{MAIN_NS}}}is")
        if inline is not None:
            values[address] = "".join(node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t"))
        elif value is None:
            values[address] = None
        elif cell.attrib.get("t") == "s":
            values[address] = shared[int(value.text)]
        elif cell.attrib.get("t") == "str":
            values[address] = value.text or ""
        else:
            number = float(value.text)
            values[address] = int(number) if number.is_integer() else number
    return values


class TemplateAssetTests(unittest.TestCase):
    def test_sanitized_single_sheet_with_three_samples(self) -> None:
        self.assertTrue(ASSET.is_file())
        with zipfile.ZipFile(ASSET) as archive:
            names = set(archive.namelist())
            self.assertFalse(any(name.startswith(("customXml/", "xl/externalLinks/")) for name in names))
            self.assertFalse(any("comments" in name.lower() for name in names))

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
            self.assertIsNotNone(sheets)
            sheet_nodes = list(sheets)
            self.assertEqual(len(sheet_nodes), 1)
            self.assertEqual(sheet_nodes[0].attrib["name"], "报销明细")
            self.assertNotEqual(sheet_nodes[0].attrib.get("state"), "hidden")

            values = cell_values(archive)
            expected_headers = ["序号", "发生期间", "类型", "人民币金额", "报销人", "备注", "实际金额", "票面金额"]
            self.assertEqual([values[f"{column}1"] for column in "ABCDEFGH"], expected_headers)
            self.assertEqual([values[f"C{row}"] for row in range(2, 5)], ["油费", "通行费", "餐饮"])
            self.assertEqual([values[f"D{row}"] for row in range(2, 5)], [100, 20, 50])
            self.assertEqual([values[f"E{row}"] for row in range(2, 5)], ["示例人员"] * 3)
            for row in range(2, 5):
                self.assertTrue(str(values[f"F{row}"]).startswith("【样例，请替换或删除】"))

            xml_text = "\n".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in names
                if name.endswith((".xml", ".rels"))
            )
            self.assertIsNone(re.search(r"[A-Za-z]:\\\\", xml_text))
            self.assertNotIn("TargetMode=\"External\"", xml_text)


if __name__ == "__main__":
    unittest.main()
