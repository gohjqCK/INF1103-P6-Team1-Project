from Resume import Resume
import copy
from Resume import Resume
from Profile import Profile
from OverallList import OverallList
from AcceptedList import AcceptedList
from RejectedList import RejectedList
from InvalidList import InvalidList
class ResumeEvaluator:
    def __init__(self,resume):
        self.outcome = resume.get_outcome
        self.score = resume.get_score

    def category(self):
        if self.outcome != "scored" or not isinstance(self.score, float):
            return "invalid"
        if self.outcome == "scored" and self.score == 0.0:
            return "rejected"
        return "accepted"


resume_list=[{
    "file": "Senior IT Manager Resume.PDF",
    "name": "JOHN H. SMITH, M.ENG.",
    "email": "info@greatresumesfast.com",
    "phone": "800.991.5187",
    "outcome": "scored",
    "score": 44.4,
    "reason": "Meets 1 of 3 rules. Missing: CCNA is listed as a certification; Has cloud experience (Ignored 2 claim(s) whose evidence did not pass the checks.)",
    "summary": "John H. Smith has over 15 years of experience in IT infrastructure and technical management, with 10 years in senior-level leadership roles. He specializes in IT infrastructure, communication, network management, system operations, service management, and disaster recovery.",
    "skills": [
      "IT Infrastructure",
      "Network Management",
      "System Operations",
      "Service Management",
      "Disaster Recovery",
      "Project Management",
      "Technical Consultation",
      "Technical Documentation",
      "Security",
      "Microsoft Certified Systems Engineer: Security (MCSE-S)",
      "Microsoft Certified Systems Administrator: Security (MCSA-S)",
      "Microsoft Certified Technology Specialist (MCTS)",
      "Project Management Professional (PMP)"
    ],
    "qualifications": [
      "Master of Engineering (M.Eng.) in Applied Electronics, STATE UNIVERSITY, UNIVERSITY OF STATE, 2000",
      "Microsoft Certified Systems Engineer: Security (MCSE-S), Windows Server 2003",
      "Microsoft Certified Systems Administrator: Security (MCSA-S), Windows Server 2003",
      "Microsoft Certified Technology Specialist (MCTS), Internet Security & Acceleration Server 2006, Configuration",
      "Microsoft Certified Technology Specialist (MCTS), Configuring Windows Vista Client",
      "Lenel OnGuard Sapphire Certification",
      "Intel Technology Expert",
      "Intel Product Integrator",
      "Project Management Professional (PMP) Training, Project Management Institute (PMI)"
    ],
    "work_experience": [
      "Global IT & Networking Technical Specialist, INFO SYSTEMS, Palm Springs, FL, 2010 - Present",
      "Technical Manager, GLOBAL INFO, Palm Springs, FL, 2002 - 2010",
      "Senior Systems Engineer, SYSTEMS CONNECT, Palm Springs, FL, 2000 - 2002",
      "Electronics Engineer, PC SYSTEMS, Palm Springs, FL, 1996 - 2000"
    ],
    "projects": [
      "Project Manager and Lead Systems Designer for multiple high-profile, large-scale network and IT infrastructure projects, INFO SYSTEMS, Palm Springs, FL",
      "Managed and maintained Windows active directory forests for several key clients, GLOBAL INFO, Palm Springs, FL",
      "Upgraded organization’s Windows NT Domain, PC SYSTEMS, Palm Springs, FL"
    ]
  },
  {
    "file": "Senior IT Project Manager Resume.pdf",
    "name": "",
    "email": "xxxxx@yahoo.co.in",
    "phone": "",
    "outcome": "scored",
    "score": 0.0,
    "reason": "Meets 0 of 3 rules. Missing: At least 2 years of networking experience; CCNA is listed as a certification; Has cloud experience",
    "summary": "A senior IT project manager with 14 years of experience, leading diverse technology projects and managing large teams. Holds multiple certifications and has managed budgets up to $8 million. Expert in IT technologies, software engineering, and project management methodologies.",
    "skills": [
      "Project Management Professional Certification (PMP)",
      "Prince2 Foundation & Practitioner Certification",
      "ITIL V2 Foundation Certification",
      "Infosys Program management (TRANSCEED) certification",
      "Infosys BRITE (Six sigma) certification",
      "Infosys Project management certification (PM ELITE)",
      "IBM – DB2 certification",
      "LOMA Step-1 and LOMA-280 certification",
      "Infosys .Net (Design & Architecture) certifications",
      "Database",
      "Legacy",
      "Web",
      "Client server",
      "Software engineering",
      "Development & testing methodologies",
      "Enterprise architecture",
      "Design patterns",
      "Estimation methodologies",
      "Quality processes",
      "IT outsourcing contracts",
      "IT service delivery management",
      "Global delivery model",
      "Multimillion-dollar projects",
      "Large project teams",
      "High-quality deliverables",
      "Communication",
      "Technical, business and financial acumen",
      "International experience",
      "IT project management"
    ],
    "qualifications": [
      "MBA Degree, Hanze University of Applied Science, Groningen, Netherlands, 2010",
      "Master of Engineering (Chemical) - (6.4/8.0 CGPA), Indian Institute of Science, Bangalore, 1997",
      "Bachelor of Engineering (Chemical) - (80% marks obtained), Utkal University, Orissa, 1995"
    ],
    "work_experience": [
      "Senior Project Manager, Infosys Technologies Ltd, Netherlands, 2007 - Present",
      "Senior Project Manager, Infosys Technologies Ltd, Mauritius DC, 2005 - 2007",
      "Project Manager, Infosys Technologies Ltd, Mauritius DC, 2003 - 2005",
      "Project Manager, Infosys Technologies Ltd, Bangalore & Lugarno, 2001 - 2002",
      "Programmer Analyst, Infosys Technologies Ltd, Bangalore & UK, 1999 - 2001",
      "Developer, Infosys Technologies Ltd, Bangalore & UK, 1995 - 1999"
    ],
    "projects": [
      "Achieved 100% on time within budget delivery of projects by implementing robust risk & quality management framework",
      "Achieved 30% cost reduction of maintenance & support projects by implementing global delivery execution and by implementing productivity and quality management best practices",
      "Implemented comprehensive Quality management & Knowledge management processes, resulting in enhancing the quality of projects delivered by 50% and ultimate customer satisfaction",
      "Achieved 20% improvement in productivity and 10% gain in schedule implementing factory model for technology migration program",
      "Achieved 100% SLA compliance, within 3 months of setting up service level agreement, resulting in absolute client satisfaction"
    ]
  },{
    "file": "Tech Professional Resume.pdf",
    "name": "Sameer Shah",
    "email": "hello@reallygreatsite.com",
    "phone": "123-456-7890",
    "outcome": "",
    "score": 0.0,
    "reason": "Meets 0 of 3 rules. Missing: At least 2 years of networking experience; CCNA is listed as a certification; Has cloud experience",
    "summary": "An IT Support Assistant with experience in digital support, file organization, and basic system management. Confident in learning new tools and following processes to support colleagues across departments.",
    "skills": [
      "IT support",
      "Helpdesk assistance",
      "Account setup",
      "Troubleshooting",
      "System documentation",
      "Digital records",
      "User support",
      "Process coordination",
      "Digital Skills Certificate",
      "Workplace IT Support Course",
      "Cyber Awareness Essentials"
    ],
    "qualifications": [
      "BTEC Diploma — Digital Skills and Business Support, Greenfield College, 2018",
      "Digital Skills Certificate, Circuit Systems, 2022",
      "Workplace IT Support Course, Streamline Systems, 2022",
      "Cyber Awareness Essentials, Cloudlet Tech, 2020"
    ],
    "work_experience": [
      "IT Support Assistant, Greenfield College, Sep 2020 – Feb 2022",
      "IT Support Assistant, Circuit Systems, Mar 2022 – Present",
      "IT Support Assistant, Cloudlet Tech, Jun 2019 – Aug 2020"
    ],
    "projects": [
      "Internal File Organisation Project: Improved document retrieval and team accessibility",
      "Basic Website Content Update Project: Updated text, checked links, ensured consistency"
    ]
  }]

resume_list_copy=copy.deepcopy(resume_list)
#to allocate stringname
combinedList={"acceptedList":[],"rejectedList":[],"invalidList":[]}
for raw_resume in resume_list_copy:
    #create a resume
    resume= Resume(raw_resume)
    #Decide which list to put the resume in
    resumeEvaluate=ResumeEvaluator(resume)
    #the return value + "List"
    stringname=str(resumeEvaluate.category())+"List"
    
    combinedList[stringname].append(resume)


acceptedList=AcceptedList()
rejectedList=RejectedList()
invalidList=InvalidList()
acceptedList.list=combinedList["acceptedList"]
rejectedList.list=combinedList["rejectedList"]
invalidList.list=combinedList["invalidList"]

overallList=OverallList()
overallList.list_overall=acceptedList.output_dict
overallList.list_overall=rejectedList.output_dict
overallList.list_overall=invalidList.output_dict
print(overallList.list_overall)


