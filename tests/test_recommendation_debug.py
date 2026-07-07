import logging
import os
import unittest
from unittest.mock import patch

from backend.services.recommendation_debug import rec_debug


class RecommendationDebugTests(unittest.TestCase):
    @patch.dict(os.environ, {"DEBUG_RECOMMENDATIONS": "true"}, clear=False)
    def test_rec_debug_logs_warning_when_enabled(self):
        with self.assertLogs("backend.services.recommendation_debug", level="WARNING") as captured:
            rec_debug("probe value=%s", 1)

        self.assertIn("recommendation_debug probe value=1", captured.output[0])

    @patch.dict(os.environ, {"DEBUG_RECOMMENDATIONS": ""}, clear=False)
    def test_rec_debug_is_silent_when_disabled(self):
        with patch.object(logging.getLogger("backend.services.recommendation_debug"), "warning") as mock_warning:
            rec_debug("probe value=%s", 1)

        mock_warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
