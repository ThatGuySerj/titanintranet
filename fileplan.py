"""The proposed electronic filing structure, as data.

TGC-SYS-EFILE-2026-01 v1.0 - the Master File Plan, owned by the CFO. Nothing
here is live. SharePoint holds none of these folders yet; this module exists so
the plan can be walked through in a browser before anybody builds it, which is
a great deal cheaper than building it and then walking through it.

The tree below is a transcription of Section 5 of the plan document and is the
only copy in this repository. Everything the page shows is derived from it:
the counts, the depth, the path lengths, the restricted list. That is
deliberate - a page that quotes "742 folders" from the document's prose while
displaying a tree with a different number in it would be worse than useless at
the one job it has, which is showing people what they are about to agree to.

    tree()      the nested structure
    payload()   everything the page needs, as one JSON-ready dict

The lettered children (A_, B_, C_ ...) under Driver Qualification Files, Unit
Files, Customer Master Files, Vendor Master Files, Owned and Leased Properties,
Well Files, Employee Files and Active Transactions are RECORD TEMPLATES. They
are not one folder each - they are the shape that gets copied for every driver,
unit, customer, vendor, property, well, employee and deal. The page says so
where they appear, because reading them as ordinary folders makes the tree look
far smaller than what actually gets deployed.
"""
import functools
import json
import re

DOC = "TGC-SYS-EFILE-2026-01"
VERSION = "1.0"
OWNER = "Derek Boothe, CFO & Vice President"
APPROVER = "Lonnie Ridenbaugh, President"
ROOT = "TITAN-GROUP"

# ---------------------------------------------------------------------------
#  Section 5 - the structure. Two spaces per level.
# ---------------------------------------------------------------------------

TREE_TEXT = """
00_FILE-PLAN-AND-GOVERNANCE
  00-01_File-Plan-Master
  00-02_Naming-Conventions-and-Doc-Codes
  00-03_Retention-and-Destruction-Schedule
  00-04_Permissions-and-Access-Matrix
  00-05_Scanning-and-Digitization-SOPs
  00-06_Legal-Holds
  00-07_Destruction-Certificates-and-Log
  00-08_System-Admin-and-Change-Log
  00-09_Templates-Library
    00-09-01_Letterhead-and-Brand-Assets
    00-09-02_Forms-Master
    00-09-03_Contract-Templates
    00-09-04_Policy-and-SOP-Templates
    00-09-05_Financial-Model-Templates
  00-10_Training-and-User-Guides
  00-11_Records-Inventory-and-Migration-Tracker
05_SCAN-INTAKE-AND-WORKFLOW
  05-01_Scan-Drop-Unfiled
  05-02_In-Process-OCR
  05-03_Quality-Check
  05-04_Ready-to-File
  05-05_Filed-Pending-Shred
  05-06_Exceptions-Illegible-or-Unidentified
  05-07_Daily-Morning-Paperwork-Batches
  05-08_Mail-and-Correspondence-Intake
10_CORPORATE-AND-LEGAL
  10-01_Entity-Records
    10-01-01_TEUI_Titan-Enterprises-Unlimited-Inc
      A_Formation-and-Charter
      B_Governing-Documents-Bylaws
      C_Ownership-and-Cap-Table
      D_Minutes-and-Resolutions
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Director-Records
      K_Dissolution-Merger-Conversion
    10-01-02_TET_Titan-Energy-Transportation-LLC
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-03_TOL_Titan-Oil-LLC
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-04_TTI_Titan-Trucking-Industries-LLC
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-05_TEL_Titan-Enterprises-Leasing-Co-LLC
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-06_TREP_Titan-Real-Estate-Properties-LLC
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-07_TPOL_Titan-Polishing-LLC-dba-Reflection-Metal-Works
      A_Formation-and-Charter
      B_Operating-Agreement
      C_Ownership-and-Membership-Interests
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Registered-Agent
      H_Foreign-Qualifications
      I_DBA-and-Trade-Names
      J_Officer-and-Manager-Records
      K_Dissolution-Merger-Conversion
    10-01-08_LRLT_Lonnie-Ridenbaugh-Living-Trust_RESTRICTED
      A_Trust-Instrument-and-Amendments
      B_Trustee-Records
      C_Assets-Held-in-Trust
      D_Correspondence
    10-01-09_KTL_Kimberley-Transport-LLC_PARTITIONED
      A_Formation-and-Charter
      B_Partnership-Operating-Agreement
      C_Ownership-and-Capital-Accounts
      D_Minutes-and-Consents
      E_Annual-Filings-and-Good-Standing
      F_EIN-and-Tax-ID
      G_Partner-Correspondence
      H_Distributions-and-Allocations
    10-01-10_Dormant-and-Reserved-Entities
  10-02_Intercompany-Agreements
    10-02-01_Management-and-Shared-Services-Agreements
    10-02-02_Equipment-Lease-Agreements-TEL
    10-02-03_Real-Estate-Lease-Agreements-TREP
    10-02-04_Intercompany-Notes-and-Loans
    10-02-05_Cost-Allocation-and-Transfer-Pricing-TEL-FIN-001
    10-02-06_Intercompany-Reconciliation-Support
    10-02-07_Guaranty-and-Support-Agreements
  10-03_Contracts-Master
    10-03-01_Customer-MSAs-and-Service-Agreements
    10-03-02_Vendor-and-Supplier-Agreements
    10-03-03_Owner-Operator-and-Lease-Purchase
    10-03-04_Broker-and-Carrier-Agreements
    10-03-05_Confidentiality-and-NDAs
    10-03-06_Third-Party-Leases
    10-03-07_Executed-Contract-Register
    10-03-08_Contracts-Expired-and-Terminated
  10-04_Litigation-and-Claims
    10-04-01_Active-Matters
    10-04-02_Closed-Matters
    10-04-03_Demand-Letters-and-Pre-Suit
    10-04-04_Subpoenas-and-Records-Requests
    10-04-05_Settlement-Agreements-and-Releases
  10-05_Intellectual-Property
    10-05-01_Trademarks-and-Trade-Names
    10-05-02_Domains-and-Digital-Assets
    10-05-03_Licenses-In-and-Out
  10-06_Governance-Policies
    10-06-01_Delegation-of-Authority
    10-06-02_Signature-Authority-Matrix
    10-06-03_Code-of-Conduct-and-Ethics
    10-06-04_Conflict-of-Interest-and-Related-Party
    10-06-05_Board-and-Member-Meeting-Calendar
  10-07_Corporate-Restructuring-Project
    10-07-01_Structure-Plan-v3-1-and-Revisions
    10-07-02_Companion-Legal-Agreements
    10-07-03_Implementation-Checklist-and-Status
    10-07-04_Advisor-Memos-and-Opinions
  10-08_Outside-Counsel
    10-08-01_Engagement-Letters
    10-08-02_Matter-Files-by-Firm
    10-08-03_Legal-Invoices-and-Budgets
20_FINANCE-AND-ACCOUNTING
  20-01_Financial-Statements
    20-01-01_Consolidated-and-Combined
    20-01-02_By-Entity
    20-01-03_Monthly-Reporting-Packages
    20-01-04_Quarterly-Packages
    20-01-05_Annual-Year-End
    20-01-06_Lender-and-Third-Party-Versions
  20-02_Month-End-Close
    20-02-01_Close-Calendar-and-Checklists
    20-02-02_Journal-Entries-and-Support
    20-02-03_Account-Reconciliations
    20-02-04_Accruals-and-Prepaids
    20-02-05_Flux-and-Variance-Analysis
    20-02-06_Intercompany-Eliminations
  20-03_General-Ledger-and-COA
    20-03-01_Chart-of-Accounts-Master
    20-03-02_Trial-Balances
    20-03-03_GL-Detail-Exports
    20-03-04_Opening-Balances-and-Conversions
  20-04_Accounts-Payable
    20-04-01_Vendor-Invoices-Paid
    20-04-02_Open-and-Pending-Payables
    20-04-03_Check-Runs-and-ACH-Batches
    20-04-04_Vendor-W9-and-1099-Reporting
    20-04-05_Fuel-and-Fluids-AP
    20-04-06_Credit-Card-Statements-and-Receipts
    20-04-07_Employee-Expense-Reports
    20-04-08_Disputes-and-Vendor-Statements
  20-05_Accounts-Receivable
    20-05-01_Customer-Invoices-Issued
    20-05-02_Field-Tickets-and-Run-Tickets-Billing-Support
    20-05-03_Aging-and-Collections
    20-05-04_Credit-Memos-and-Adjustments
    20-05-05_Customer-Credit-Applications-and-References
    20-05-06_Lien-Notices-and-Preliminary-Notices
    20-05-07_Cash-Application-and-Remittance-Advices
    20-05-08_Bad-Debt-and-Write-Offs
  20-06_Payroll-Accounting_RESTRICTED
    20-06-01_Payroll-Registers
    20-06-02_Payroll-Tax-Deposits
    20-06-03_Garnishments-and-Withholding-Orders
    20-06-04_401k-and-Benefit-Remittances
    20-06-05_Driver-Settlements-and-Owner-Operator-Pay
    20-06-06_Payroll-Reconciliations
  20-07_Fixed-Assets-and-Depreciation
    20-07-01_Fixed-Asset-Register
    20-07-02_Additions-and-Capitalization-Support
    20-07-03_Disposals-and-Gain-Loss
    20-07-04_Depreciation-Schedules-Book-and-Tax
    20-07-05_Impairment-and-Valuation
  20-08_Debt-and-Lease-Schedules
    20-08-01_Debt-Amortization-Schedules
    20-08-02_Lease-Schedules-and-ASC-842
    20-08-03_Interest-and-Fee-Accruals
  20-09_Budget-and-Forecast
    20-09-01_Annual-Operating-Budget
    20-09-02_Capital-Expenditure-Budget
    20-09-03_Rolling-Forecast-and-Reforecast
    20-09-04_Budget-to-Actual-Reporting
  20-10_Cost-Accounting-and-Unit-Economics
    20-10-01_Cost-Per-Mile-and-Cost-Per-Hour
    20-10-02_Cost-Per-Barrel-Water-Division
    20-10-03_Per-Unit-and-Per-Driver-Profitability
    20-10-04_Division-and-Yard-Level-PandL
    20-10-05_Job-and-Customer-Profitability
  20-11_Audit-Review-and-Compilation
    20-11-01_Engagement-Letters
    20-11-02_PBC-Requests-and-Deliverables
    20-11-03_Workpapers-Provided
    20-11-04_Management-Letters-and-Responses
    20-11-05_Issued-Reports
  20-12_Cash-Management
    20-12-01_Daily-Cash-Position
    20-12-02_Thirteen-Week-Cash-Flow
    20-12-03_Cash-Forecast-Support
  20-13_Accounting-Policies-and-SOPs
  20-14_Financial-Systems-and-Data
    20-14-01_ERP-Accounting-System-Documentation
    20-14-02_Data-Exports-and-Backups
    20-14-03_System-Change-Log
30_TAX
  30-01_Federal-Income-Tax
    30-01-01_Returns-by-Entity-and-Year
    30-01-02_K-1s-Issued-and-Received
    30-01-03_Extensions-and-Estimates
    30-01-04_Workpapers-and-Tax-Basis-Schedules
    30-01-05_Elections-and-Statements
  30-02_State-and-Local-Income-and-Franchise
    30-02-01_Ohio
    30-02-02_West-Virginia
    30-02-03_Pennsylvania
    30-02-04_Other-States
    30-02-05_Municipal-and-School-District
  30-03_Ohio-Commercial-Activity-Tax-CAT
  30-04_Sales-and-Use-Tax
    30-04-01_Exemption-Certificates-Issued-to-Vendors
    30-04-02_Exemption-Certificates-Received-from-Customers
    30-04-03_Returns-and-Remittances
    30-04-04_Nexus-and-Registration-Analysis
    30-04-05_Audit-Defense-and-Assessments
    30-04-06_Taxability-Matrices-and-Research
  30-05_Fuel-Tax-and-IFTA
    30-05-01_IFTA-Quarterly-Returns
    30-05-02_Mileage-and-Jurisdiction-Reports
    30-05-03_Fuel-Purchase-Records
    30-05-04_IFTA-Audits
  30-06_Heavy-Highway-Use-Tax-Form-2290
  30-07_Property-Tax
    30-07-01_Real-Property
    30-07-02_Personal-Property
    30-07-03_Valuation-Appeals
  30-08_Payroll-Tax-Filings
    30-08-01_Form-941-and-940
    30-08-02_W-2-and-W-3
    30-08-03_Ohio-Withholding-and-ODJFS
    30-08-04_Multistate-Withholding
  30-09_Tax-Notices-and-Correspondence
  30-10_Tax-Planning-and-Memos
    30-10-01_Entity-and-Structure-Planning
    30-10-02_Depreciation-and-Bonus-Strategy
    30-10-03_Cost-Segregation-Studies
    30-10-04_Credits-and-Incentives
  30-11_Tax-Advisor-Engagements
40_BANKING-AND-CAPITAL
  40-01_Bank-Accounts
    40-01-01_Account-Opening-and-Signature-Cards
    40-01-02_Bank-Statements-by-Entity-and-Account
    40-01-03_Bank-Reconciliations
    40-01-04_Account-Closures
  40-02_Lender-Relationships
    40-02-01_Farmers-National-Bank
      A_Credit-Requests-and-Applications
      B_Term-Sheets-and-Commitments
      C_Executed-Loan-Documents
      D_Covenant-Compliance-Certificates
      E_Borrowing-Base-Certificates
      F_Reporting-Packages-Submitted
      G_Correspondence
      H_Collateral-and-Appraisals
    40-02-02_Peoples-Bank
      A_Credit-Requests-and-Applications
      B_Term-Sheets-and-Commitments
      C_Executed-Loan-Documents
      D_Covenant-Compliance-Certificates
      E_Borrowing-Base-Certificates
      F_Reporting-Packages-Submitted
      G_Correspondence
      H_Collateral-and-Appraisals
    40-02-03_Equipment-Finance-Lenders-and-Lessors
    40-02-04_Prospective-and-Declined-Lenders
    40-02-05_Lender-Reporting-Calendar
  40-03_Active-Loan-and-Lease-Files
  40-04_Paid-Off-and-Closed-Facilities
  40-05_UCC-Filings-and-Lien-Searches
  40-06_Guaranties-Subordinations-and-Intercreditor
  40-07_Equity-and-Investor-Relations
    40-07-01_Capital-Participation-Expand-Energy-GWS
    40-07-02_Private-Equity-Outreach-and-NDAs
    40-07-03_Valuation-and-EBITDA-Analyses
    40-07-04_Distribution-and-Contribution-Records
  40-08_Treasury-and-Merchant-Services
    40-08-01_Positive-Pay-and-Fraud-Controls
    40-08-02_Wire-and-ACH-Authorizations
    40-08-03_Fuel-and-Purchasing-Card-Programs
  40-09_Personal-Financial-Statements_RESTRICTED
  40-10_Credit-Files-and-Ratings
50_INSURANCE-AND-RISK
  50-01_Policies-in-Force
    50-01-01_Commercial-Auto-Liability
    50-01-02_General-Liability
    50-01-03_Excess-and-Umbrella
    50-01-04_Motor-Truck-Cargo
    50-01-05_Property-and-Inland-Marine
    50-01-06_Pollution-and-Environmental-Liability
    50-01-07_Workers-Compensation-Ohio-BWC
    50-01-08_Cyber-Liability
    50-01-09_Employment-Practices-EPLI
    50-01-10_Directors-and-Officers
    50-01-11_Surety-Bonds-and-Financial-Responsibility-BMC-91
    50-01-12_Employee-Benefits-Liability
  50-02_Expired-Policies-Archive
  50-03_Certificates-of-Insurance
    50-03-01_COIs-Issued-to-Customers
    50-03-02_COIs-Received-from-Vendors-and-Subcontractors
    50-03-03_Additional-Insured-and-Waiver-Endorsements
    50-03-04_COI-Tracking-Log
  50-04_Claims
    50-04-01_Auto-Open
    50-04-02_Auto-Closed
    50-04-03_Workers-Compensation-Open_RESTRICTED
    50-04-04_Workers-Compensation-Closed_RESTRICTED
    50-04-05_Property-and-Equipment
    50-04-06_Cargo
    50-04-07_Environmental-and-Pollution
    50-04-08_General-Liability
  50-05_Loss-Runs-and-Experience-Modification
  50-06_Renewal-Submissions-and-Applications
  50-07_Broker-and-Carrier-Correspondence
  50-08_Ohio-BWC-Administration
    50-08-01_Payroll-True-Up-Reports
    50-08-02_Group-Rating-and-Program-Enrollment
    50-08-03_MCO-and-TPA-Records
  50-09_Risk-Register-and-Business-Continuity
  50-10_Contractual-Risk-Review-and-Indemnity-Analysis
60_HUMAN-RESOURCES_RESTRICTED
  60-01_Employee-Files-Active
    A_Application-Resume-and-Onboarding
    B_Offer-Compensation-and-Job-Changes
    C_Performance-Reviews
    D_Discipline-and-Corrective-Action
    E_Policy-Acknowledgments-and-Signed-Forms
    F_Separation-and-Exit
  60-02_Employee-Files-Terminated
  60-03_I-9-Files_SEGREGATED
    60-03-01_Active-Employees
    60-03-02_Terminated-Employees
    60-03-03_E-Verify-Records
    60-03-04_Reverification-Tickler
  60-04_Confidential-Medical-Files_SEGREGATED
    60-04-01_DOT-Physical-Medical-Detail
    60-04-02_FMLA-and-Leave-Documentation
    60-04-03_ADA-Accommodation-Requests
    60-04-04_Workers-Compensation-Medical
    60-04-05_Benefits-Enrollment-and-PHI
  60-05_Payroll-HR-Administration
    60-05-01_Timekeeping-Records
    60-05-02_PTO-and-Leave-Balances
    60-05-03_Pay-Rate-Change-Authorizations
    60-05-04_Direct-Deposit-and-W-4
  60-06_Benefits-Administration
    60-06-01_Plan-Documents-and-SPDs
    60-06-02_Carrier-Contracts-and-Invoices
    60-06-03_Form-5500-and-Compliance-Filings
    60-06-04_401k-Plan-Administration
    60-06-05_COBRA-and-ACA-Reporting
    60-06-06_Open-Enrollment-Materials
  60-07_Recruiting-and-Applicant-Flow
    60-07-01_Job-Postings-and-Requisitions
    60-07-02_Applications-Not-Hired
    60-07-03_Driver-Recruiting-Campaigns
    60-07-04_Recruiting-Vendors-and-Job-Boards
    60-07-05_Referral-and-Sign-On-Bonus-Programs
  60-08_Handbook-and-HR-Policies
  60-09_Training-and-Certifications-Non-DOT
  60-10_Org-Charts-and-Job-Descriptions
  60-11_Labor-Law-Postings-and-Compliance
  60-12_Unemployment-and-Wage-Claims
  60-13_Investigations-and-Complaints_RESTRICTED
  60-14_Compensation-Studies-and-Pay-Bands
70_SAFETY-AND-DOT-COMPLIANCE
  70-01_Driver-Qualification-Files
    A_Employment-Application-391-21
    B_Motor-Vehicle-Record-Annual
    C_Road-Test-or-CDL-Equivalency
    D_Medical-Examiner-Certificate-and-CDLIS
    E_Previous-Employer-Safety-Performance-History
    F_Annual-Review-and-Violation-Certification
    G_Entry-Level-Driver-Training-Certificate
    H_Hazmat-and-Tanker-Endorsements
    I_Disqualification-and-Reinstatement
  70-02_Drug-and-Alcohol-Program_RESTRICTED
    70-02-01_Policy-and-Employee-Acknowledgments
    70-02-02_Random-Selection-Pool-and-Logs
    70-02-03_Pre-Employment-Tests
    70-02-04_Random-Test-Results
    70-02-05_Post-Accident-Tests
    70-02-06_Reasonable-Suspicion-Tests
    70-02-07_Return-to-Duty-and-Follow-Up
    70-02-08_FMCSA-Clearinghouse-Queries-and-Reports
    70-02-09_MRO-and-Consortium-TPA-Records
    70-02-10_Supervisor-Reasonable-Suspicion-Training
    70-02-11_Annual-MIS-Reports
  70-03_Hours-of-Service-and-ELD
    70-03-01_Records-of-Duty-Status
    70-03-02_Supporting-Documents
    70-03-03_Unassigned-Driving-Time
    70-03-04_Log-Edits-and-Annotations
    70-03-05_ELD-Malfunction-Log-and-Paper-Logs
    70-03-06_HOS-Violation-Reports-and-Coaching
  70-04_Accidents-and-Incidents
    70-04-01_Accident-Register-390-15
    70-04-02_Accident-Files-by-Incident
    70-04-03_DOT-Recordable-Determinations
    70-04-04_Post-Accident-Testing-Documentation
    70-04-05_Root-Cause-and-Corrective-Action
    70-04-06_Near-Miss-Reports
    70-04-07_Preventability-Review-Committee
  70-05_Inspections-and-Enforcement
    70-05-01_Roadside-Inspection-Reports
    70-05-02_Violation-Corrections-and-Signed-Returns
    70-05-03_DOT-Audits-and-Compliance-Reviews
    70-05-04_CSA-Scores-and-BASIC-Reports
    70-05-05_DataQs-Challenges
    70-05-06_MSHA-Contractor-V438
    70-05-07_State-and-PUCO-Enforcement
  70-06_Vehicle-Maintenance-Compliance-Files
    70-06-01_Annual-Periodic-Inspections-396-17
    70-06-02_Driver-Vehicle-Inspection-Reports-DVIR
    70-06-03_Systematic-Maintenance-Records-396-3
    70-06-04_Brake-Inspector-Qualifications
    70-06-05_Out-of-Service-and-Repair-Verification
  70-07_Operating-Authority-and-Registration
    70-07-01_USDOT-Number-and-MCS-150
    70-07-02_Motor-Carrier-Authority-MC
    70-07-03_Unified-Carrier-Registration-UCR
    70-07-04_IRP-Apportioned-Registration
    70-07-05_IFTA-License-and-Decals
    70-07-06_Ohio-BMV-Registration
    70-07-07_PUCO-and-State-Permits
    70-07-08_Oversize-Overweight-Permits
    70-07-09_Hazmat-Registration-and-Security-Plan
    70-07-10_Process-Agent-BOC-3
  70-08_Safety-Meetings-and-Training
    70-08-01_Toolbox-Talks-and-Attendance
    70-08-02_New-Driver-Orientation
    70-08-03_Remedial-and-Post-Incident-Training
    70-08-04_Certificates-and-Completion-Records
  70-09_Safety-Policies-and-SOPs
  70-10_OSHA-and-Workplace-Safety
    70-10-01_OSHA-300-301-and-300A-Logs
    70-10-02_Safety-Data-Sheets-SDS
    70-10-03_Job-Safety-Analyses-and-JHAs
    70-10-04_PPE-and-Respirator-Program
    70-10-05_Lockout-Tagout-and-Confined-Space
    70-10-06_OSHA-Inspections-and-Citations
  70-11_Field-Environmental-Compliance
    70-11-01_Spill-Prevention-SPCC-Plans
    70-11-02_Spill-Response-Reports
    70-11-03_Emergency-Response-Plans
  70-12_Customer-Safety-Qualification-Platforms
    70-12-01_ISNetworld
    70-12-02_Avetta
    70-12-03_Veriforce-and-PEC
    70-12-04_Customer-Specific-Prequalification
80_FLEET-AND-EQUIPMENT
  80-01_Unit-Files-by-Unit-Number
    A_Title-and-Ownership
    B_Registration-and-Plates
    C_Purchase-or-Lease-Documents
    D_Specifications-and-Build-Sheet
    E_Warranty-and-Recalls
    F_Photos-and-Condition-Reports
    G_Modifications-and-Upfits
    H_Disposal-and-Sale
  80-02_Titles-and-Registration-Master
    80-02-01_Original-Title-Custody-Log
    80-02-02_Lien-Releases
    80-02-03_Title-Transfers-Intercompany
    80-02-04_Plate-and-Cab-Card-Records
  80-03_Maintenance-and-Repair
    80-03-01_Preventive-Maintenance-Schedules
    80-03-02_Internal-Work-Orders
    80-03-03_Outside-Vendor-Repair-Invoices
    80-03-04_Warranty-Claims
    80-03-05_Tire-Program-and-Records
    80-03-06_Tank-Testing-and-Certifications
    80-03-07_Breakdown-and-Roadside-Assistance
  80-04_Parts-and-Inventory
    80-04-01_Parts-Purchase-Orders
    80-04-02_Inventory-Counts-and-Valuation
    80-04-03_Parts-Vendor-Catalogs-and-Pricing
    80-04-04_Core-Returns-and-Credits
  80-05_Fuel-Program
    80-05-01_Fuel-Vendor-RJ-Wright-and-Sons
    80-05-02_Fuel-Card-Administration
    80-05-03_Bulk-Tank-Records-and-Inventory
    80-05-04_Fuel-Purchase-Detail-and-Reconciliation
    80-05-05_Def-and-Lubricants
  80-06_Telematics-and-Cameras
    80-06-01_Motive-Deployment-and-Configuration
    80-06-02_Device-Assignment-by-Unit
    80-06-03_Video-Event-Pulls-and-Retention
    80-06-04_Telematics-Reporting
    80-06-05_Prior-System-Records
  80-07_Acquisitions-and-Dispositions
    80-07-01_Quotes-and-Purchase-Approvals
    80-07-02_New-Unit-Deliveries
    80-07-03_Trade-Ins-and-Auctions
    80-07-04_Total-Loss-and-Salvage
    80-07-05_Fire-Damaged-and-Out-of-Service-Units
  80-08_Intercompany-Equipment-Transfers
    80-08-01_Transfer-Authorizations
    80-08-02_Bills-of-Sale-and-Valuations
    80-08-03_Lease-Schedule-Amendments
  80-09_Trailers-Tanks-and-Ancillary-Equipment
  80-10_Fleet-Reporting-and-Analytics
    80-10-01_Utilization-Reports
    80-10-02_Maintenance-Cost-Per-Mile
    80-10-03_Downtime-and-Availability
    80-10-04_Fleet-Roster-Master
  80-11_Equipment-Manuals-and-Reference
90_OPERATIONS
  90-01_Dispatch
    90-01-01_Daily-Dispatch-Sheets
    90-01-02_Driver-Assignment-and-Scheduling
    90-01-03_Load-Confirmations
    90-01-04_Dispatch-SOPs-and-Scripts
    90-01-05_After-Hours-and-On-Call
  90-02_Field-and-Run-Tickets
    90-02-01_Water-Division-TET
    90-02-02_Crude-Division-Titan-Oil
    90-02-03_Dump-and-Aggregate-TTI
    90-02-04_Livestock-Kimberley-Transport
    90-02-05_Disposal-and-Manifest-Tickets
  90-03_Daily-and-Weekly-Operating-Reports
  90-04_Yard-Operations
    90-04-01_Barnesville
    90-04-02_Cambridge
    90-04-03_Sherrodsville
    90-04-04_New-Philadelphia
    90-04-05_Sardis
    90-04-06_Newcomerstown
    90-04-07_Coshocton
  90-05_Customer-Site-Requirements-and-Access
  90-06_Capacity-and-Utilization-Planning
  90-07_Owner-Operators-and-Contract-Carriers
    90-07-01_Carrier-Qualification-Packets
    90-07-02_Settlements-and-Rate-Confirmations
    90-07-03_Insurance-and-Authority-Verification
  90-08_Operations-SOPs-and-Work-Instructions
  90-09_Quality-and-Customer-Service-Issues
  90-10_Weather-Road-Closures-and-Disruption-Logs
100_SALES-CUSTOMERS-AND-REVENUE
  100-01_Customer-Master-Files
    A_Contracts-and-MSAs
    B_Rate-Sheets-and-Amendments
    C_Insurance-and-Indemnity-Requirements
    D_Billing-Requirements-and-Portal-Access
    E_Contacts-and-Org-Charts
    F_Correspondence
    G_Performance-and-Scorecards
  100-02_Rate-Cards-and-Pricing
    100-02-01_Published-Rate-Schedules
    100-02-02_Rate-Increase-Requests-and-Support
    100-02-03_Fuel-Surcharge-Programs
    100-02-04_Accessorial-and-Demurrage-Schedules
    100-02-05_Competitive-Rate-Benchmarking
  100-03_Bids-RFPs-and-Proposals
    100-03-01_Active-Bids
    100-03-02_Won
    100-03-03_Lost-and-No-Bid
  100-04_Revenue-Reporting
    100-04-01_Revenue-by-Customer
    100-04-02_Revenue-by-Division
    100-04-03_Revenue-by-Yard
    100-04-04_Volume-and-Load-Count-Reporting
  100-05_Marketing-and-Brand
    100-05-01_Logo-and-Brand-Standards
    100-05-02_Website-and-Digital
    100-05-03_Driver-Recruiting-Marketing
    100-05-04_Truck-Graphics-and-Signage
    100-05-05_Trade-Shows-and-Sponsorships
  100-06_Customer-Onboarding-and-Setup
  100-07_CRM-and-Prospect-Pipeline
110_VENDORS-AND-PROCUREMENT
  110-01_Vendor-Master-Files
    A_W-9-and-Tax-Documentation
    B_Certificates-of-Insurance
    C_Contracts-and-Terms
    D_Pricing-Agreements
    E_Contacts
    F_Performance-and-Issues
  110-02_Purchase-Orders-and-Requisitions
  110-03_Quotes-and-Bids-Received
  110-04_Vendor-Onboarding-and-Compliance
  110-05_Subcontractors-and-Third-Party-Carriers
  110-06_Procurement-Policies-and-Approval-Thresholds
  110-07_Preferred-Vendor-and-National-Account-Programs
120_REAL-ESTATE-AND-FACILITIES
  120-01_Owned-Properties
    A_Deed-and-Title-Policy
    B_Survey-and-Legal-Description
    C_Purchase-and-Closing-Binder
    D_Appraisals-and-Valuations
    E_Environmental-Phase-I-and-II
    F_Mortgage-and-Financing
    G_Property-Tax
    H_Insurance
  120-02_Leased-Properties
    A_Lease-and-Amendments
    B_Rent-Schedule-and-Payments
    C_Landlord-Correspondence
    D_Estoppels-and-SNDAs
  120-03_Yard-Site-Files
  120-04_Utilities-and-Services
  120-05_Construction-and-Capital-Improvements
  120-06_Zoning-Permits-and-Easements
  120-07_Facility-Maintenance-and-Vendors
  120-08_Security-Access-and-Keys
130_SWD-WELLS-AND-ENVIRONMENTAL
  130-01_Well-Files-by-API-Number
    A_UIC-Class-II-Permit-and-Application
    B_ODNR-Correspondence-and-Orders
    C_Drilling-Completion-and-Logs
    D_Mechanical-Integrity-Testing-MIT
    E_Injection-Volume-and-Pressure-Reports
    F_Wellhead-Equipment-and-Facility
    G_Bonding-and-Financial-Assurance
    H_Plugging-and-Abandonment
    I_Title-Lease-and-Surface-Rights
  130-02_ODNR-Division-of-Oil-and-Gas-Regulatory
  130-03_US-EPA-UIC-Program
  130-04_Ohio-EPA
  130-05_Disposal-Volume-Reporting-and-Manifests
  130-06_Landowner-Leases-and-Royalty
  130-07_Well-Acquisitions-and-Transfers
  130-08_Environmental-Assessments-and-Remediation
  130-09_Spill-and-Release-Notifications
  130-10_Seismicity-Monitoring-and-Compliance
  130-11_Water-Sourcing-and-Recycling
140_IT-AND-SYSTEMS
  140-01_Systems-Inventory-and-Licenses
  140-02_Software-Vendor-Contracts-and-SaaS
  140-03_Access-and-Identity-Management
    140-03-01_User-Provisioning-and-Deprovisioning
    140-03-02_Permission-Change-Requests
    140-03-03_Access-Reviews
  140-04_Backup-and-Disaster-Recovery
  140-05_Cybersecurity-and-Incident-Response
    140-05-01_Policies-and-Standards
    140-05-02_Security-Assessments-and-Pen-Tests
    140-05-03_Incident-Reports
    140-05-04_Security-Awareness-Training
    140-05-05_Cyber-Insurance-Requirements
  140-06_Hardware-and-Device-Inventory
  140-07_Integrations-and-Data-Mapping
  140-08_IT-Project-Files
  140-09_Telecom-and-Connectivity
  140-10_Email-Archiving-and-Retention
150_STRATEGIC-MA-AND-PROJECTS
  150-01_Active-Transactions
    A_NDA-and-Confidentiality
    B_Letters-of-Intent-and-Term-Sheets
    C_Diligence-Received-from-Target
    D_Diligence-Provided
    E_Valuation-and-Financial-Models
    F_Purchase-and-Sale-Agreements
    G_Third-Party-Advisors
    H_Closing-Binder-and-Funds-Flow
    I_Post-Closing-and-Integration
  150-02_Closed-Transactions-Archive
  150-03_Pipeline-and-Target-Screening
  150-04_Exit-Readiness-Data-Room
    150-04-01_Corporate-and-Legal
    150-04-02_Financial-and-Quality-of-Earnings
    150-04-03_Tax
    150-04-04_Operations-and-Customers
    150-04-05_Fleet-and-Assets
    150-04-06_HR-and-Benefits
    150-04-07_Safety-and-Regulatory-Compliance
    150-04-08_Environmental-and-SWD
    150-04-09_Insurance-and-Litigation
    150-04-10_IT-and-Systems
    150-04-11_Diligence-Response-Tracker
  150-05_Strategic-Planning-and-Board-Materials
  150-06_Special-Projects
160_ARCHIVE-AND-INACTIVE
  160-01_Closed-and-Dissolved-Entities
  160-02_Superseded-Records
  160-03_Scanned-Paper-Backfile-by-Year
  160-04_Records-Under-Legal-Hold
  160-05_Pending-Destruction-Review
"""

# ---------------------------------------------------------------------------
#  Section 3 - what each master folder is for, and who owns it
# ---------------------------------------------------------------------------

MASTERS = {
    "00": ("CFO", "The rules of the system itself - file plan, naming, "
                  "retention, permissions, templates, legal holds."),
    "05": ("Controller", "The paper-to-electronic conveyor belt. A working "
                         "area only - nothing lives here permanently."),
    "10": ("CFO", "Entity records, intercompany agreements, contracts, "
                  "litigation, governance, restructuring."),
    "20": ("Controller", "Financials, close, GL, AP, AR, payroll accounting, "
                         "fixed assets, budget, unit economics."),
    "30": ("CFO", "Federal, state, local, sales and use, IFTA, 2290, "
                  "property, payroll tax, planning."),
    "40": ("CFO", "Bank accounts, lender relationships, loan files, UCCs, "
                  "equity, treasury."),
    "50": ("Safety / CFO", "Policies, COIs, claims, loss runs, BWC, the risk "
                           "register."),
    "60": ("HR", "Employee files, I-9, confidential medical, benefits, "
                 "recruiting, the handbook."),
    "70": ("Safety / DOT", "DQFs, drug and alcohol, HOS and ELD, accidents, "
                           "inspections, authority, OSHA."),
    "80": ("Dir. Fleet Admin & Purchasing",
           "Unit files, titles, maintenance, parts, fuel, telematics, "
           "transfers."),
    "90": ("Head of Dispatch", "Dispatch, field and run tickets, operating "
                               "reports, yards, owner-operators."),
    "100": ("CFO", "Customer master files, rate cards, bids, revenue "
                   "reporting, marketing."),
    "110": ("Dir. Fleet Admin & Purchasing",
            "Vendor master files, POs, quotes, subcontractors."),
    "120": ("CFO", "Owned and leased property, yard sites, construction, "
                   "permits."),
    "130": ("CFO", "Well files by API, ODNR and EPA, injection reporting, "
                   "landowner leases."),
    "140": ("Technology contact", "Systems inventory, SaaS contracts, access "
                                  "management, backup, cybersecurity."),
    "150": ("CFO", "Active deals, closed deals, pipeline, the exit-readiness "
                   "data room."),
    "160": ("Controller", "Closed entities, superseded records, the scanned "
                          "backfile, legal hold, pending destruction."),
}

# ---------------------------------------------------------------------------
#  Section 7 - the permissions matrix
# ---------------------------------------------------------------------------

ROLES = ["Owner / President", "CFO", "Controller", "Sr. Accountant", "HR",
         "Safety / DOT", "Fleet / Purchasing", "Dispatch", "Yard Manager"]

# F = full, E = edit, R = read, "-" = no access. The tenth column is external
# and is a sentence rather than a letter, so it is kept separately.
MATRIX = {
    "00":  ("R F E R R R R R R", "none"),
    "05":  ("R F F E E E E E E", "none"),
    "10":  ("F F R - - - - - -", "Counsel: edit"),
    "20":  ("R F F E - - R - -", "CPA: read"),
    "30":  ("R F E R - - - - -", "CPA: edit"),
    "40":  ("F F E R - - - - -", "Lender: read, staged"),
    "50":  ("R F E R R E R R R", "Broker: edit"),
    "60":  ("R R - - F - - - -", "none"),
    "70":  ("R E R - R F R R R", "Auditor: read"),
    "80":  ("R E R R - R F R E", "none"),
    "90":  ("R E R R - R R F E", "none"),
    "100": ("R F E E - - - R -", "none"),
    "110": ("R E E E - - F - R", "none"),
    "120": ("F F R - - - R - R", "none"),
    "130": ("F F R - - E - - -", "Consultant: edit"),
    "140": ("R E R - - - - - -", "MSP: full"),
    "150": ("F F - - - - - - -", "Advisor: edit, staged"),
    "160": ("R F F R - - - - -", "none"),
}

# ---------------------------------------------------------------------------
#  Section 7.1 - why a folder is walled off. Keyed by folder name.
# ---------------------------------------------------------------------------

WHY = {
    "60_HUMAN-RESOURCES_RESTRICTED": (
        "HR only",
        "Everything below this point is a personnel record. The whole master "
        "folder is restricted and three folders inside it are walled off "
        "again."),
    "60-03_I-9-Files_SEGREGATED": (
        "HR only",
        "I-9s have to be stored apart from personnel files so they can be "
        "handed to ICE without the rest of an employee's record going with "
        "them."),
    "60-04_Confidential-Medical-Files_SEGREGATED": (
        "HR only",
        "The ADA and OSHA 1910.1020 both require medical information to sit "
        "in a separate confidential file rather than the personnel file."),
    "60-13_Investigations-and-Complaints_RESTRICTED": (
        "HR and CFO",
        "Harassment and retaliation exposure. Who can open the folder is "
        "itself a fact a plaintiff's lawyer will ask about."),
    "70-02_Drug-and-Alcohol-Program_RESTRICTED": (
        "DOT / Safety and CFO",
        "49 CFR 382.401 requires secure storage with access limited to people "
        "with a need to know."),
    "50-04-03_Workers-Compensation-Open_RESTRICTED": (
        "HR and CFO", "Contains medical information."),
    "50-04-04_Workers-Compensation-Closed_RESTRICTED": (
        "HR and CFO", "Contains medical information."),
    "20-06_Payroll-Accounting_RESTRICTED": (
        "CFO, Controller and HR", "Compensation confidentiality."),
    "40-09_Personal-Financial-Statements_RESTRICTED": (
        "Owner and CFO", "The owner's personal financial data."),
    "10-01-08_LRLT_Lonnie-Ridenbaugh-Living-Trust_RESTRICTED": (
        "Owner, CFO and counsel", "Trust and estate planning."),
    "10-01-09_KTL_Kimberley-Transport-LLC_PARTITIONED": (
        "CFO and the KTL partner",
        "A third-party 80/20 partnership. Filing these inside Titan's general "
        "tree creates both a partnership dispute and a consolidation question "
        "at exit."),
    "150_STRATEGIC-MA-AND-PROJECTS": (
        "Owner and CFO", "Deal confidentiality and NDA obligations."),
}

# The record templates: the eight parents Section 5 names, whose lettered
# children are copied once per record rather than existing once.
#
# Not every lettered folder is a template. The entity folders under 10-01 and
# the two lenders under 40-02 use the same lettered shape, but each of those is
# a real folder that exists once - they are enumerated, not copied. Calling
# them templates on the page would tell somebody that a folder per entity gets
# created on demand, which is the opposite of what the entity wall is for.
TEMPLATE_OF = {
    "60-01_Employee-Files-Active": "every employee",
    "70-01_Driver-Qualification-Files": "every driver",
    "80-01_Unit-Files-by-Unit-Number": "every unit",
    "100-01_Customer-Master-Files": "every customer",
    "110-01_Vendor-Master-Files": "every vendor",
    "120-01_Owned-Properties": "every owned property",
    "120-02_Leased-Properties": "every leased property",
    "130-01_Well-Files-by-API-Number": "every well",
    "150-01_Active-Transactions": "every deal",
}

# Where the lettered shape repeats across siblings that each exist once.
REPEATED_UNDER = {
    "10-01_Entity-Records": "every entity",
    "40-02_Lender-Relationships": "each lender",
}

ENTITIES = [
    ("TEUI", "Titan Enterprises Unlimited, Inc.",
     "Holdco - target structure (v3.1), not yet implemented"),
    ("TET", "Titan Energy Transportation LLC",
     "Active - frac and produced water hauling"),
    ("TOL", "Titan Oil LLC", "Active - crude hauling (Marathon / MPLX)"),
    ("TTI", "Titan Trucking Industries LLC",
     "Active - dump truck and MSHA, contractor ID V438"),
    ("TEL", "Titan Enterprises Leasing Co. LLC",
     "Active - equipment titling and lessor"),
    ("TREP", "Titan Real Estate Properties LLC", "Active"),
    ("TPOL", "Titan Polishing LLC (d/b/a Reflection Metal Works)", "Active"),
    ("LRLT", "Lonnie Ridenbaugh Living Trust", "Restricted access"),
    ("KTL", "Kimberley Transport LLC",
     "80/20 partnership - third party, partitioned"),
    ("TGC", "Titan Group - shared and consolidated", "Cross-entity records"),
]

YARDS = [("BAR", "Barnesville"), ("CAM", "Cambridge"),
         ("SHR", "Sherrodsville"), ("NPH", "New Philadelphia"),
         ("SAR", "Sardis"), ("NEW", "Newcomerstown"), ("COS", "Coshocton")]

NAMING = {
    "pattern": "YYYY-MM-DD_ENTITY_DOCTYPE_PARTY-OR-SUBJECT_IDENTIFIER_vN.ext",
    "rules": [
        "Date first, always ISO YYYY-MM-DD. The document's effective date, not "
        "the day it was scanned.",
        "Underscores separate fields. Hyphens separate words inside a field.",
        "No spaces, and none of & / \\ : * ? \" < > | # % - SharePoint "
        "rejects several of them outright.",
        "Versions are _v1, _v2. A final executed version is _EXEC.",
        "One hundred characters maximum for the filename.",
    ],
    "examples": [
        "2026-09-14_TET_INV_EOG-Resources_INV-10482_v1.pdf",
        "2026-08-31_TOL_FS_Monthly-Financial-Statements_v2.xlsx",
        "2026-07-01_TEL_LEASE_TET-Equipment-Schedule-B_EXEC.pdf",
        "2026-09-02_TGC_SOP_BMV-Fleet-Compliance_TGC-SOP-BMV-2026-01_v1.docx",
        "2026-06-15_TTI_COI_Ascent-Resources_Additional-Insured.pdf",
    ],
    "records": [
        ("Driver", "LASTNAME-FIRSTINITIAL_Hire-YYYY-MM-DD",
         "LASTNAME-FIRSTINITIAL_MVR_2026-04-02.pdf"),
        ("Unit", "UNIT-0142_2021-Peterbilt-579",
         "UNIT-0142_TITLE_2021-03-11.pdf"),
        ("Customer", "EOG-Resources", "EOG-Resources_MSA_2025-01-15_EXEC.pdf"),
        ("Vendor", "RJ-Wright-and-Sons",
         "RJ-Wright-and-Sons_W9_2026-01-08.pdf"),
        ("Well", "API-34-059-XXXXX_Hill-1",
         "API-34-059-XXXXX_MIT_2026-05-20.pdf"),
        ("Property", "New-Concord-HQ_140-S-Friendship-Dr",
         "New-Concord-HQ_DEED_2019-08-02.pdf"),
        ("Transaction", "Devco-Oil-and-Trucking", "Devco_LOI_2026-04-10_v3.pdf"),
    ],
    "codes": [
        ("AGR", "Agreement"), ("APP", "Application"), ("AUD", "Audit document"),
        ("BS", "Balance Sheet"), ("CERT", "Certificate"),
        ("COI", "Certificate of Insurance"), ("CORR", "Correspondence"),
        ("DEED", "Deed"), ("DQF", "Driver Qualification document"),
        ("DVIR", "Driver Vehicle Inspection Report"),
        ("ELD", "ELD / HOS record"), ("FS", "Financial Statement"),
        ("FT", "Field / Run Ticket"), ("INSP", "Inspection report"),
        ("INS", "Insurance policy"), ("INV", "Invoice"),
        ("LOI", "Letter of Intent"), ("MEMO", "Memorandum"),
        ("MIN", "Minutes"), ("MVR", "Motor Vehicle Record"),
        ("NDA", "Non-Disclosure Agreement"), ("PO", "Purchase Order"),
        ("POL", "Policy"), ("RES", "Resolution"), ("RPT", "Report"),
        ("SCH", "Schedule"), ("SOP", "Standard Operating Procedure"),
        ("STMT", "Statement"), ("TITLE", "Certificate of Title"),
        ("TR", "Tax Return"),
    ],
}

PRINCIPLES = [
    ("Function first, entity second",
     "Top-level folders are organised by what the business does, not by which "
     "company did it. Entity separation appears inside the functions where "
     "legal separateness is actually tested - corporate records, tax, "
     "banking, insurance, financial statements. Nine near-identical trees "
     "would be the alternative."),
    ("Numbered master folders",
     "Every master folder keeps a fixed number. Numbers never change and are "
     "never reused, so the sort order is the same in every system. The gaps "
     "(01-04, 06-09, 11-19) are there so a new master folder can be added "
     "without renumbering everything after it."),
    ("Shallow and wide",
     "Four levels, no more. SharePoint stops at 400 characters for the whole "
     "path including the filename, and deep nesting is the single most common "
     "way a corporate file migration fails."),
    ("A template for anything that repeats",
     "Drivers, units, customers, vendors, properties, wells, employees and "
     "deals all get the same lettered shape. Copy it, rename it, and every "
     "driver file looks like every other driver file - which is what makes a "
     "DQF audit survivable."),
    ("Restricted zones are structural",
     "A folder ending in _RESTRICTED, _SEGREGATED or _PARTITIONED has its "
     "permission inheritance broken before the first document goes in. "
     "Several are legal requirements rather than preferences."),
    ("Folders for structure, metadata for retrieval",
     "Folders are the skeleton and the audit trail. Columns - Entity, Yard, "
     "Division, Customer, Unit No., Fiscal Year, Document Type, Retention "
     "Class - are how anybody actually finds anything. Do not try to encode "
     "every attribute in the folder name."),
]

WORKFLOW = [
    ("05-01_Scan-Drop-Unfiled", "Any staff",
     "The scanner drops its output here. No naming required yet."),
    ("05-02_In-Process-OCR", "Controller",
     "OCR applied, a searchable PDF/A created."),
    ("05-03_Quality-Check", "Controller",
     "Legibility, page count and completeness checked against the paper."),
    ("05-04_Ready-to-File", "Assigned staff", "Renamed to the convention."),
    ("Moved out", "Assigned staff",
     "Into its permanent home somewhere in 10 to 150."),
    ("05-05_Filed-Pending-Shred", "Controller",
     "Originals held thirty days, then shredded - except the do-not-destroy "
     "list."),
    ("05-06_Exceptions", "Controller",
     "Rescanned, or sent back to the department it came from, weekly."),
]

RISKS = [
    ("The holdco does not exist yet",
     "10-01-01_TEUI is built to the v3.1 target structure, but Titan "
     "Enterprises Unlimited has not been formed. Nothing bearing a TEUI label "
     "should be filed there before the formation date - a diligence reviewer "
     "who finds TEUI documents predating formation reads the whole structure "
     "as cosmetic."),
    ("Entity separateness is tested in the files",
     "TET and TREP are owned personally as disregarded SMLLCs. If invoices, "
     "bank statements and insurance certificates sit in undifferentiated "
     "folders, the separate-entities argument weakens in a veil-piercing "
     "claim. The entity level inside 10, 20, 30, 40 and 50 is doing real "
     "legal work."),
    ("Kimberley Transport is a third party",
     "KTL is an 80/20 partnership. Its records are partitioned and the "
     "partner's rights need confirming with counsel - what he is entitled to "
     "see, and what Titan may keep."),
    ("HR files are almost certainly commingled today",
     "I-9s, medical records, DOT physicals and workers' comp documents in one "
     "manila folder per employee is an ICE finding and an ADA exposure. "
     "Splitting them is a document-by-document job, not a bulk scan, and it "
     "is the highest-risk item in the migration."),
    ("Equipment transfer documentation gaps are already known",
     "80-08 will start out largely empty. Filling it in retroactively, with "
     "counsel on what can be papered after the fact, is a workstream rather "
     "than a filing task."),
    ("Telematics video retention needs a written policy",
     "Video is discoverable. A vendor default with no company policy behind "
     "it is a bad position either way - too short looks like spoliation, too "
     "long builds a searchable archive of every hard brake."),
    ("Path length will bite if the plan is modified",
     "A fifth level, or staff creating free-form subfolders, produces files "
     "that sync locally and then fail to upload. Folder creation below level "
     "three belongs to the Controller and the technology contact."),
    ("The retention periods are not confirmed yet",
     "They reflect the standard federal and Ohio requirements but have not "
     "been through Titan's counsel or CPA. Nothing gets shredded on the "
     "strength of this document alone."),
]

# ---------------------------------------------------------------------------
#  Parsing
# ---------------------------------------------------------------------------

_LETTER = re.compile(r"^[A-Z]_")
_SUFFIX = {"_RESTRICTED": "restricted", "_SEGREGATED": "segregated",
           "_PARTITIONED": "partitioned"}


def _wall(name):
    """restricted / segregated / partitioned, or None."""
    for suffix, kind in _SUFFIX.items():
        if name.endswith(suffix):
            return kind
    return None


def _number(name):
    """The number prefix - 00, 10-01, 70-02-08 - or "" for a lettered one."""
    head = name.split("_", 1)[0]
    return head if re.match(r"^[0-9][0-9-]*$", head) else ""


def _title(name):
    """The folder name as prose. 70-02_Drug-and-Alcohol-Program -> the words.

    The numbers and the underscores are how the system sorts; they are not how
    anybody reads. The page shows both.

    Not every hyphen is a word separator, which is why this is not one call to
    replace(). 60-03_I-9-Files would come out as "I 9 Files", and a page that
    renames the I-9 file is a page nobody in HR will trust about anything else.
    A hyphen is kept between two numbers (396-17, 300-301) and after a single
    capital letter (I-9, W-2, K-1s, E-Verify); everywhere else it is a space.

    THE BROWSER HAS A COPY OF THIS RULE, in fileplan.html. test_fileplan.py
    runs both over every folder in the tree and compares, so the two cannot
    drift apart quietly.
    """
    body = name.split("_", 1)[1] if "_" in name else name
    for suffix in _SUFFIX:
        if body.endswith(suffix):
            body = body[:-len(suffix)]

    parts = body.split("-")
    out = parts[0]
    for prev, nxt in zip(parts, parts[1:]):
        keep = ((prev[-1:].isdigit() and nxt[:1].isdigit())
                or (len(prev) == 1 and prev.isalpha() and prev.isupper()))
        out += ("-" if keep else " ") + nxt
    return out


@functools.lru_cache(maxsize=1)
def tree():
    """The structure, nested. Each node:

        name     as it appears on disk
        title    the same thing, readable
        num      the number prefix, or "" for a record-template letter
        path     TITAN-GROUP/... - what SharePoint will see
        depth    1 for a master folder
        wall     restricted / segregated / partitioned, inherited downwards
        own      True when the wall is this folder's own, not inherited
        letter   True when this is one of the lettered folders
        tmpl     what the lettered children get copied for, on the parent
        rep      what the lettered shape below repeats across, on the
                 grandparent - entities and lenders, which are enumerated
                 rather than copied
        kids     children
    """
    root = {"name": ROOT, "title": "Titan Group", "num": "", "path": ROOT,
            "depth": 0, "wall": None, "own": False, "letter": False,
            "tmpl": None, "rep": None, "kids": []}
    stack = [(-1, root)]

    for line in TREE_TEXT.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        name = line.strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        wall = _wall(name)
        node = {
            "name": name,
            "title": _title(name),
            "num": _number(name),
            "path": parent["path"] + "/" + name,
            "depth": parent["depth"] + 1,
            "wall": wall or parent["wall"],
            "own": bool(wall),
            "letter": bool(_LETTER.match(name)),
            "tmpl": TEMPLATE_OF.get(name),
            "rep": REPEATED_UNDER.get(parent["name"]),
            "kids": [],
        }
        parent["kids"].append(node)
        stack.append((indent, node))

    return root


def walk(node=None):
    node = tree() if node is None else node
    yield node
    for kid in node["kids"]:
        for x in walk(kid):
            yield x


def stats():
    """Counted from the tree, not quoted from the document's prose."""
    nodes = [n for n in walk() if n["depth"] > 0]
    letters = [n for n in nodes if n["letter"]]
    return {
        "folders": len(nodes),
        "masters": len([n for n in nodes if n["depth"] == 1]),
        "depth": max(n["depth"] for n in nodes),
        "walled": len([n for n in nodes if n["wall"]]),
        "own_walls": len([n for n in nodes if n["own"]]),
        "templates": len(TEMPLATE_OF),
        "template_folders": len(letters),
        "longest": max(len(n["path"]) for n in nodes),
        "longest_path": max((n["path"] for n in nodes), key=len),
        "empty": len([n for n in nodes if not n["kids"]]),
    }


def _thin(node):
    """The tree as the page wants it - short keys, nothing it will not use.

    The readable title and the full path are both left out on purpose: each is
    derivable from the name and the ancestry, and carrying them would put a
    third of this page's weight on the wire twice over. The page rebuilds them
    in two lines of JavaScript.
    """
    out = {"n": node["name"]}
    if node["wall"]:
        out["w"] = node["wall"]
        if node["own"]:
            out["o"] = 1
    if node["letter"]:
        out["L"] = 1
    if node["tmpl"]:
        out["tm"] = node["tmpl"]
    if node["rep"]:
        out["rp"] = node["rep"]
    if node["name"] in WHY:
        out["why"] = {"who": WHY[node["name"]][0], "text": WHY[node["name"]][1]}
    if node["kids"]:
        out["k"] = [_thin(k) for k in node["kids"]]
    return out


def payload():
    """Everything the page needs, in one dict."""
    masters = []
    for node in tree()["kids"]:
        num = node["num"]
        owner, about = MASTERS.get(num, ("", ""))
        letters, external = MATRIX.get(num, ("", ""))
        masters.append({
            "num": num,
            "name": node["name"],
            "title": node["title"],
            "owner": owner,
            "about": about,
            "access": dict(zip(ROLES, letters.split())),
            "external": external,
            "wall": node["wall"],
        })

    return {
        "doc": DOC, "version": VERSION, "owner": OWNER, "approver": APPROVER,
        "root": ROOT,
        "stats": stats(),
        "roles": ROLES,
        "masters": masters,
        "tree": [_thin(n) for n in tree()["kids"]],
        "entities": [{"code": c, "name": n, "status": s}
                     for c, n, s in ENTITIES],
        "yards": [{"code": c, "name": n} for c, n in YARDS],
        "naming": NAMING,
        "principles": [{"head": h, "text": t} for h, t in PRINCIPLES],
        "workflow": [{"folder": f, "owner": o, "what": w}
                     for f, o, w in WORKFLOW],
        "risks": [{"head": h, "text": t} for h, t in RISKS],
    }


def as_json():
    return json.dumps(payload(), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    s = stats()
    print("%(folders)s folders, %(masters)s master folders, "
          "%(depth)s levels deep" % s)
    print("%(walled)s inside a wall, %(own_walls)s of them walled off "
          "themselves" % s)
    print("longest path %(longest)s characters:" % s)
    print("  " + s["longest_path"])
    print("%s characters of JSON" % len(as_json()))
