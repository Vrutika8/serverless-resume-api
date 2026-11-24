import json
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError

os.environ.setdefault("TABLE_NAME", "test-table")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import handler  # noqa: E402


def api_event(resource):
    return {"resource": resource, "httpMethod": "GET"}


def stored(section, item_id, **attributes):
    return {"section": section, "itemId": item_id, **attributes}


class HandlerTests(unittest.TestCase):
    def test_personal_returns_single_object_without_key_attributes(self):
        items = [stored("personal", "profile", name="Ada")]
        with patch.object(handler, "query_section", return_value=items):
            response = handler.lambda_handler(api_event("/personal"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"name": "Ada"})

    def test_list_sections_return_ordered_lists(self):
        items = [stored("experience", "001", role="A"), stored("experience", "002", role="B")]
        with patch.object(handler, "query_section", return_value=items):
            response = handler.lambda_handler(api_event("/experience"), None)
        self.assertEqual(json.loads(response["body"]), [{"role": "A"}, {"role": "B"}])

    def test_decimal_values_are_serialised(self):
        items = [stored("education", "001", years=Decimal("4"), gpa=Decimal("8.5"))]
        with patch.object(handler, "query_section", return_value=items):
            response = handler.lambda_handler(api_event("/education"), None)
        self.assertEqual(json.loads(response["body"]), [{"years": 4, "gpa": 8.5}])

    def test_resume_route_combines_all_sections(self):
        with patch.object(handler, "query_section", return_value=[]):
            response = handler.lambda_handler(api_event("/resume"), None)
        body = json.loads(response["body"])
        self.assertEqual(set(body), {"personal", "experience", "education", "skills"})

    def test_empty_table_falls_back_to_resume_json(self):
        fallback = handler.load_fallback_data()
        with patch.object(handler, "query_section", return_value=[]):
            response = handler.lambda_handler(api_event("/skills"), None)
        self.assertEqual(json.loads(response["body"]), fallback["skills"])

    def test_unknown_route_returns_404(self):
        response = handler.lambda_handler(api_event("/unknown"), None)
        self.assertEqual(response["statusCode"], 404)

    def test_dynamodb_error_returns_500_without_details(self):
        error = ClientError({"Error": {"Code": "Boom", "Message": "secret"}}, "Query")
        with patch.object(handler, "query_section", side_effect=error):
            response = handler.lambda_handler(api_event("/personal"), None)
        self.assertEqual(response["statusCode"], 500)
        self.assertNotIn("secret", response["body"])


if __name__ == "__main__":
    unittest.main()
