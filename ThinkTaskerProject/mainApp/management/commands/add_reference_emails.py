from django.core.management.base import BaseCommand
from mainApp.models import ReferenceDocument

SAMPLE_EMAILS = [
    {
        "subject": "Issue on Panel",
        "body": "We got the information from the vendor that panel AICCP is not working properly. May we know if you have received this issue before? If yes, is this issue can be fixed by the driver? Please advise on the next steps."
    },
    {
        "subject": "ECRB Ticket Update",
        "body": "I don't know why you generated 2 SRMS records for N3GX8087P. Please rename one of them for no more use as the title and build id."
    },
    {
        "subject": "Driver exe file cannot install successfully",
        "body": "The driver exe file cannot install successfully. Please check the attached log file for details. Can you please help to fix this issue?"
    },
    {
        "subject": "ECRB Ticket Process Request",
        "body": "Do you create readme replace ticket for this case? We need to build it and test it ASAP."
    },
    {
        "subject": "iGfx Driver Weekly Team Meeting",
        "body": "Hi Team, the attached is the status chart I used today. Also tracking issues are listed here. Please check and let me know if you have any questions. Thanks."
    },
    {
        "subject": "Driver WU warning",
        "body": "You are invited to attend the product demo scheduled next Wednesday at 2 PM."
    },
    {
        "subject": "WU Warning: Driver Installation",
        "body": "For TBT driver, my understanding is except for P16 Gen2 and P1 Gen6 that supports both Win11 and Win10, all other platforms only support Win10. We should restrict OS as MinOS and MaxOS set to VB."
    },
    {
        "subject": "Request for Driver Debug Logs",
        "body": "Could you please provide the debug logs for the failed installation case? We need more information to proceed with the investigation."
    },
    {
        "subject": "Build ID Clarification Needed",
        "body": "There seems to be a mismatch in the reported build ID for the latest release. Please confirm the correct build ID and update the ticket accordingly."
    },
    {
        "subject": "Panel Compatibility Inquiry",
        "body": "Has the new panel been tested with the current driver version? If not, please schedule the compatibility tests this week."
    },
    {
        "subject": "Test Result Submission",
        "body": "Please submit your test results for the latest driver build by end of day tomorrow. Include any issues found during the tests."
    },
    {
        "subject": "Meeting Reminder: ECRB Weekly Sync",
        "body": "This is a reminder for our ECRB weekly sync meeting tomorrow at 3PM. Please prepare your progress updates and bring any open issues for discussion."
    },
    {
        "subject": "SRMS Record Deletion Request",
        "body": "If the second SRMS record is no longer needed, kindly proceed with deletion to avoid confusion in future audits."
    },
    {
        "subject": "Update Required: ReadMe Documentation",
        "body": "Please update the ReadMe documentation to reflect the latest changes in the driver installation process. Assign the ticket to the documentation team once completed."
    },
    {
        "subject": "Installation Guide Feedback",
        "body": "I encountered unclear steps in the driver installation guide. Can you revise section 3.2 and include additional troubleshooting tips?"
    },
    {
        "subject": "Vendor Coordination: Panel Replacement",
        "body": "The vendor suggested a panel replacement due to recurring failures. Please coordinate with the procurement team and update the ticket once the replacement is scheduled."
    },
    {
        "subject": "Immediate Attention: Regression in Latest Build",
        "body": "A critical regression was identified in the latest driver build affecting display output. The issue needs immediate attention. Please assign the ticket to the development team."
    },{
        "subject": "QA Approval Needed for Release",
        "body": "The QA testing for the new graphics driver build is now complete. Please review the attached report and approve the release if all issues have been addressed."
    },
    {
        "subject": "System Downtime Notification",
        "body": "There will be a scheduled downtime on Friday from 10 PM to 2 AM for server maintenance. Please plan your work accordingly and save all progress before the downtime window."
    },
    {
        "subject": "Action Required: Bug Report Submission",
        "body": "All team members are requested to submit any open bug reports for the new panel firmware by the end of this week."
    },
    {
        "subject": "Driver Rollback Request",
        "body": "Due to a newly discovered incompatibility, please roll back the graphics driver on all test machines to the previous stable version until further notice."
    },
    {
        "subject": "Reminder: Weekly Status Report",
        "body": "This is a reminder to submit your weekly status report by Friday EOD. If you have any blockers or urgent issues, please highlight them in your report."
    },
    {
        "subject": "Security Update Required",
        "body": "A new security vulnerability has been detected in the network drivers. Please update all relevant components and confirm completion by replying to this email."
    },
    {
        "subject": "Follow-up: Open Action Items",
        "body": "Following our last project review, several action items remain open. Please update the shared tracker with your progress or expected completion dates."
    },
    {
        "subject": "Approval Needed: Vendor Quotation",
        "body": "The quotation from the panel vendor is attached for your review. Please provide your approval or feedback before we proceed with the purchase."
    },
    {
        "subject": "Document Review Request",
        "body": "The updated integration guide is ready for review. Kindly check sections 4 and 5 for technical accuracy and suggest any necessary changes."
    },
    {
        "subject": "Cross-team Meeting Invitation",
        "body": "You are invited to a cross-team meeting on Thursday at 1:30 PM to discuss the upcoming driver certification process and address any questions."
    },
        {
        "subject": "Test Case Review Needed",
        "body": "Please review the updated test cases for the upcoming driver release. Let me know if you find any gaps or suggest any additional coverage."
    },
    {
        "subject": "Test Execution Results",
        "body": "The results from the automated regression suite are attached. Several failures were detected in the new driver version—please investigate the root causes."
    },
    {
        "subject": "Request for QA Validation",
        "body": "QA validation is required for the patch build before we proceed to release. Please complete validation and update the ticket with your sign-off."
    },
    {
        "subject": "Bug Reproduction Steps Required",
        "body": "Could you please provide detailed steps to reproduce the reported issue with panel calibration? The QA team is unable to replicate the bug as described."
    },
    {
        "subject": "Test Environment Setup",
        "body": "Before starting the new round of testing, ensure that your test environment is updated with the latest build and all previous test data is cleared."
    },
    {
        "subject": "Test Plan Submission",
        "body": "Please submit your test plan for the new driver features by Wednesday. Include both manual and automated test scenarios."
    },
    {
        "subject": "Testing Blocker: Missing Dependencies",
        "body": "Testing is currently blocked due to missing system dependencies. Please resolve these issues or provide the required files as soon as possible."
    },
    {
        "subject": "Test Completion Notification",
        "body": "All test cases for the patch have been executed and passed. The results are available in the shared QA report. Please confirm if any further testing is required."
    },
    {
        "subject": "Request for Additional Test Scenarios",
        "body": "With the new feature additions, please propose any additional test scenarios you think should be covered in this cycle."
    },
    {
        "subject": "Critical Bug Found During Testing",
        "body": "A critical bug affecting device initialization was found during stress testing. Please prioritize this issue for immediate investigation and provide a fix."
    },
    {
        "subject": "Test Metrics Required",
        "body": "For our upcoming release review, please compile and send the test metrics, including pass rate, coverage, and open defect counts."
    },
    {
        "subject": "Peer Review: Test Scripts",
        "body": "Requesting peer review of the new Python test scripts for the integration test suite. Please comment on any issues or improvement suggestions."
    },
    {
        "subject": "Schedule for User Acceptance Testing (UAT)",
        "body": "UAT is scheduled for next Monday. Please prepare all required test data and ensure all stakeholders are available for feedback."
    },
    {
        "subject": "Test Coverage Report Available",
        "body": "The latest code coverage report is now available for review. Please analyze any untested code paths and plan additional tests if necessary."
    },
    {
        "subject": "Testing Results: Edge Cases",
        "body": "Testing of edge cases revealed inconsistencies in error handling. Please review the test logs and suggest code improvements."
    },
        {
        "subject": "Team Performance Review Preparation",
        "body": "Please prepare your self-assessment and send your completed form to your manager by Friday. Performance review meetings will be scheduled next week."
    },
    {
        "subject": "Project Milestone Update",
        "body": "Kindly submit your milestone status update to the project manager by end of day. Highlight any risks or resource constraints."
    },
    {
        "subject": "Budget Approval Needed",
        "body": "The quarterly budget proposal is attached for your review and approval. Please send your feedback or approval before the finance team’s deadline."
    },
    {
        "subject": "Strategy Meeting Invitation",
        "body": "You are invited to attend the strategic planning meeting scheduled for Thursday at 10 AM. Please prepare discussion points regarding project timelines and resource allocation."
    },
    {
        "subject": "Annual Leave Planning",
        "body": "Managers, please collect your team members’ planned annual leave dates and submit the consolidated schedule to HR by next Monday."
    },
    {
        "subject": "Resource Allocation Request",
        "body": "The development team requires two additional testers for the next sprint. Please confirm if resources can be reallocated."
    },
    {
        "subject": "Risk Assessment Required",
        "body": "Please complete the risk assessment for the new product launch and submit your report to the management committee by this Friday."
    },
    {
        "subject": "Project Closure Checklist",
        "body": "As we approach project completion, please review the closure checklist and confirm that all deliverables have been met. Send your final sign-off to the PMO."
    },
    {
        "subject": "Department All-Hands Meeting",
        "body": "The next department all-hands meeting is scheduled for Tuesday at 2 PM. Attendance is mandatory. Please submit any topics or questions you want addressed."
    },
    {
        "subject": "Mentorship Program Participation",
        "body": "We are launching a new mentorship program. If you are interested in becoming a mentor or mentee, please register using the attached form by next week."
    },
    {
        "subject": "Performance Improvement Plan",
        "body": "This is a reminder to schedule a meeting with your direct report to review their performance improvement plan progress and provide feedback."
    },
    {
        "subject": "Succession Planning Update",
        "body": "Managers, please update your succession plans for key roles in your teams and send the revised documents to HR by the end of the quarter."
    },
    {
        "subject": "Client Feedback Review",
        "body": "The latest client satisfaction survey results are in. Please review the feedback and prepare action items for service improvement."
    },
    {
        "subject": "Quarterly Business Review Preparation",
        "body": "Please consolidate your team’s achievements, challenges, and upcoming goals for the quarterly business review next week."
    },
    {
        "subject": "Onboarding Checklist for New Hires",
        "body": "Ensure all tasks on the onboarding checklist are completed for new hires. Update HR with the completion status."
    },
    {
        "subject": "Policy Update Communication",
        "body": "A new company policy regarding remote work has been released. Please read the attached document and communicate any questions to your manager."
    },
    {
        "subject": "Executive Summary Submission",
        "body": "Project leads, please submit your executive summary reports to upper management by end of day tomorrow for inclusion in the board packet."
    },
    {
        "subject": "Budget Reforecast Required",
        "body": "Due to changing project priorities, please reforecast your departmental budget and send the updated figures to Finance by Thursday."
    },
    {
        "subject": "Manager’s One-on-One Scheduling",
        "body": "All managers are reminded to schedule one-on-one meetings with each team member before the end of the month. Confirm your schedules in the shared calendar."
    },
    {
        "subject": "Performance Award Nominations",
        "body": "Nominations for quarterly performance awards are now open. Please submit your nominations by the end of the week."
    },
]

class Command(BaseCommand):
    help = "Bulk add sample reference emails to ReferenceDocument"

    def handle(self, *args, **options):
        count = 0
        for email in SAMPLE_EMAILS:
            ref_doc, created = ReferenceDocument.objects.get_or_create(
                subject=email["subject"],
                body=email["body"],
            )
            if created:
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Added {count} reference emails."))
