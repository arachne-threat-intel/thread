from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import REPORT_TECHNIQUES_MINIMUM
from unittest.mock import AsyncMock
from uuid import uuid4


class TestRestService(ThreadAppTest):
    async def test_low_quality_check_should_return_when_report_does_not_exist(self):
        """
        Function to check if `remove_report_if_low_quality` method returns
        when there is no report with the provided ID.
        """
        # Arrange
        report_id = str(uuid4())
        self.data_svc.get_report_by_id_or_title = AsyncMock(return_value=[])
        self.data_svc.get_report_unique_techniques_count = AsyncMock()
        self.data_svc.remove_report_by_id = AsyncMock()

        # Act
        await self.rest_svc.remove_report_if_low_quality(report_id=report_id)

        # Assert
        self.data_svc.get_report_by_id_or_title.assert_called_once_with(by_id=True, report=report_id)
        self.data_svc.get_report_unique_techniques_count.assert_not_called()
        self.data_svc.remove_report_by_id.assert_not_called()

    async def test_low_quality_check_should_not_remove_report_when_not_automatically_generated(self):
        """
        Function to check if `remove_report_if_low_quality` method does not remove the report
        when it has not been automatically generated.
        """
        # Arrange
        report_id = str(uuid4())
        report = dict(automatically_generated=self.dao.db_false_val)
        self.data_svc.get_report_by_id_or_title = AsyncMock(return_value=[report])
        self.data_svc.get_report_unique_techniques_count = AsyncMock()
        self.data_svc.remove_report_by_id = AsyncMock()

        # Act
        await self.rest_svc.remove_report_if_low_quality(report_id=report_id)

        # Assert
        self.data_svc.get_report_by_id_or_title.assert_called_once_with(by_id=True, report=report_id)
        self.data_svc.get_report_unique_techniques_count.assert_not_called()
        self.data_svc.remove_report_by_id.assert_not_called()

    async def test_low_quality_check_should_remove_report_when_techniques_found_less_than_minimum(self):
        """
        Function to check if `remove_report_if_low_quality` method removes the report
        when it has been automatically generated and
        has less than minimum amount required of techniques found.
        """
        # Arrange
        report_id = str(uuid4())
        report = dict(automatically_generated=self.dao.db_true_val, url="oh.no/low-quality")
        self.data_svc.get_report_by_id_or_title = AsyncMock(return_value=[report])
        unique_techniques_count = REPORT_TECHNIQUES_MINIMUM - 1
        self.data_svc.get_report_unique_techniques_count = AsyncMock(return_value=unique_techniques_count)
        self.data_svc.remove_report_by_id = AsyncMock()

        # Act
        with self.assertLogs() as captured:
            await self.rest_svc.remove_report_if_low_quality(report_id=report_id)

        # Assert
        self.data_svc.get_report_by_id_or_title.assert_called_once_with(by_id=True, report=report_id)
        self.data_svc.get_report_unique_techniques_count.assert_called_once_with(report_id=report_id)
        self.data_svc.remove_report_by_id.assert_called_once_with(report_id=report_id)
        self.assertEqual(len(captured.records), 1)
        self.assertIn(
            f"Deleted report with {unique_techniques_count} technique(s) found: {report['url']}",
            captured.records[0].getMessage(),
        )

    async def test_low_quality_check_should_not_remove_report_when_techniques_found_greater_than_minimum(self):
        """
        Function to check if `remove_report_if_low_quality` method does not remove the report
        when it has been automatically generated and
        has more than minimum amount required of techniques found.
        """
        # Arrange
        report_id = str(uuid4())
        report = dict(automatically_generated=self.dao.db_true_val)
        self.data_svc.get_report_by_id_or_title = AsyncMock(return_value=[report])
        unique_techniques_count = REPORT_TECHNIQUES_MINIMUM + 1
        self.data_svc.get_report_unique_techniques_count = AsyncMock(return_value=unique_techniques_count)
        self.data_svc.remove_report_by_id = AsyncMock()

        # Act
        with self.assertLogs() as captured:
            await self.rest_svc.remove_report_if_low_quality(report_id=report_id)

        # Assert
        self.data_svc.get_report_by_id_or_title.assert_called_once_with(by_id=True, report=report_id)
        self.data_svc.get_report_unique_techniques_count.assert_called_once_with(report_id=report_id)
        self.data_svc.remove_report_by_id.assert_not_called()
        self.assertEqual(len(captured.records), 1)
        self.assertIn(
            f"{unique_techniques_count} technique(s) found for report {report_id}", captured.records[0].getMessage()
        )

    async def test_low_quality_check_should_not_remove_report_when_techniques_found_equals_minimum(self):
        """ "
        Function to check if `remove_report_if_low_quality` method does not remove the report
        when it has been automatically generated and
        has exactly the minimum amount required of techniques found.
        """
        # Arrange
        report_id = str(uuid4())
        report = dict(automatically_generated=self.dao.db_true_val)
        self.data_svc.get_report_by_id_or_title = AsyncMock(return_value=[report])
        unique_techniques_count = REPORT_TECHNIQUES_MINIMUM
        self.data_svc.get_report_unique_techniques_count = AsyncMock(return_value=unique_techniques_count)
        self.data_svc.remove_report_by_id = AsyncMock()

        # Act
        with self.assertLogs() as captured:
            await self.rest_svc.remove_report_if_low_quality(report_id=report_id)

        # Assert
        self.data_svc.get_report_by_id_or_title.assert_called_once_with(by_id=True, report=report_id)
        self.data_svc.get_report_unique_techniques_count.assert_called_once_with(report_id=report_id)
        self.data_svc.remove_report_by_id.assert_not_called()
        self.assertEqual(len(captured.records), 1)
        self.assertIn(
            f"{unique_techniques_count} technique(s) found for report {report_id}", captured.records[0].getMessage()
        )
