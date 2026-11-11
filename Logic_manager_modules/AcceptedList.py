from Logic_manager_modules.FilteredList import FilteredList
from Logic_manager_modules.Output_dict import Output_dict
from Logic_manager_modules.Sort_score import Sort_score
from Logic_manager_modules.Profile import Profile
from Logic_manager_modules.Resume import Resume
#Format is accepted: [profile1],[profile2]
class AcceptedList(FilteredList,Output_dict,Sort_score):
    def __init__(self):
        super().__init__()

    @property
    def show_profiles(self):
        profile_list=[]
        for profile in self.__resume_list:
            profile_contents=profile.get_profile
            profile_list.append(profile_contents)
        return profile_list

    @property
    def list(self):
        return self.__resume_list
    
    @list.setter
    def list(self,resume):
        self.__resume_list=resume

    #Abstract method
    @property
    def output_dict(self):
        return {"accepted":self.list_to_profile}

    @property
    def sort_score(self):
        self.list.sort(key=lambda res: res.get_score, reverse=True)
        #sort_list= sorted(self.list, )
        return self.list_to_profile

##Test data

'''
list1=AcceptedList()
dict1={
    "file": "Adriana-Rosario-IT-Manager-Resume (TechieCV.com).pdf",
    "name": "Adriana Rosario",
    "email": "itmanager@gmail.com",
    "phone": "+1 414-555-0182",
    "outcome": "scored",
    "score": 22.2,
    "reason": "Meets 1 of 3 rules. Missing: At least 2 years of networking experience; CCNA is listed as a certification (Ignored 1 claim(s) whose evidence did not pass the checks.)",
    "summary": "IT Manager with 13 years of experience in leading IT operations for Fortune-500 financial services, healthcare, and regulated enterprise IT, specializing in IT strategy, service delivery, and budget ownership. Holds a B.B.A. in Management Information Systems from the University of Wisconsin-Madison and has extensive experience in service management, collaboration, infrastructure, and security.",
    "skills": [
      "ITIL 4",
      "Agile-ITSM hybrid",
      "change management",
      "problem management",
      "service request management",
      "Microsoft 365",
      "Entra ID",
      "ServiceNow",
      "SOC 2 Type II",
      "ISO 27001",
      "HIPAA",
      "PMP",
      "service management tools",
      "security and compliance"
    ],
    "qualifications": [
      "B.B.A. in Management Information Systems, University of Wisconsin-Madison, 2013"
    ],
    "work_experience": [
      "IT Manager, Northwestern Mutual, Milwaukee, WI, Jul 2020 - Present",
      "IT Manager, Aurora Health Care, Milwaukee, WI, Jul 2015 - Jun 2020"
    ],
    "projects": [
      "3-year IT roadmap for Northwestern Mutual",
      "Entra ID migration for Aurora Health Care",
      "ERP module rollout for Aurora Health Care",
      "M&A IT integration for Aurora Health Care"
    ]
  }
dict2={
    "file": "Assistant IT Manager Resume.pdf",
    "name": "JOHN H. SMITH",
    "email": "info@greatresumesfast.com",
    "phone": "800.991.5187",
    "outcome": "scored",
    "score": 0.0,
    "reason": "Meets 0 of 3 rules. Missing: At least 2 years of networking experience; CCNA is listed as a certification; Has cloud experience (Ignored 3 claim(s) whose evidence did not pass the checks.)",
    "summary": "Versatile and hands-on Project Manager with extensive experience in managing complex IT modernization and system integration projects. Skilled in strategic planning, business process design, and leading cross-functional teams to deliver rapid results.",
    "skills": [
      "Project Management",
      "Strategic Planning",
      "Business Process Design",
      "IT Infrastructure & Standardization",
      "Strategic Planning & Tactical Execution",
      "Business Transformation Solutions",
      "Business Continuity & Systems Security",
      "Large-Scale Project Management",
      "Budget Management & Cost Containment",
      "Risk Management & Risk Mitigation",
      "Leadership & Performance Enhancement",
      "Analytical Problem Solving Abilities",
      "Team Collaboration, Coaching, & Motivation"
    ],
    "qualifications": [
      "Bachelor of Business Administration —Management Information systems, State University, Waikiki, Hawaii",
      "Information Technology Infrastructure Library (ITIL) Foundations certification, License No. ITIL/HJ445123",
      "PMP Training (Project Management Professional), Tech-Pro Consulting Ltd, Japan"
    ],
    "work_experience": [
      "VP of Information Technology —Asia Pacific, Brinkley Insurance Company Ltd., Japan (2008—2012)",
      "IT/BUSINESS INTEGRATION MANAGER —Asia Pacific, Pacific Regional Ltd., Japan (2007—2008)",
      "REGIONAL MANAGER, IT Service Delivery —Asia Pacific, BNX South Pacific Assurance Co. Ltd., Japan (2006)",
      "PROJECT MANAGER —Asia Pacific, Canon Tech Solutions Ltd., Japan (2001—2005)",
      "ROLLOUT PROJECT MANAGER/CONSULTANT, META Ltd., Japan (2000—2001)",
      "REGIONAL PROJECT MANAGER/REGIONAL IS/IT MANAGER —Asia Pacific, Resource Asia Pacific Ltd., Japan, China (1990—2000)"
    ],
    "projects": [
      "Led and implemented complex projects and Global teams —mitigated risks, managed requirements, and worked with project stakeholders while managing expectations at the department and project levels.",
      "Directed the relocation of a regional data center and company regional office from Japan to Thailand; devised startup planning and managed operations within given resources, time, and budget.",
      "Managed global teams including up to 10 direct and indirect reports; developed staffing plans, managed workloads, defined deliverables, hired resources, conducted performance reviews, and ensured compliance with established company policies.",
      "Captured 60% in cost savings through a virtualization project that substantially reduced the carbon footprint from over 15 servers to less than 5 servers supporting the entire Asia Pacific region.",
      "Spearheaded the One Notes Server consolidation and migration project—reduced server usage from 9 One Notes servers to only 1 server; improved performance and reduced maintenance efforts of engineering staff.",
      "Championed a new, virtual support team for level II support—provided Regional support and substantial cost-savings.",
      "Led a team of 45 Level I and Level II help desk support team members providing outstanding quality IT services to 10 countries throughout Asia Pacific and serving a user base of more than 2,000.",
      "Led and monitored several projects with varying levels of complexity; identified and mitigated potential risks, determined project scope, managed requirements, and managed resources to support internal software development projects.",
      "Directed critical, time-sensitive Windows upgrade project to support Airline Information Systems—integrated 40 offices in the Asia Pacific region within budget in only 8 months.",
      "Managed a team of 8 project team members in the migration and rollout of Asia Pacific nodes for communications network in Japan, Hong Kong, Michigan and Brazil.",
      "Ensured Y2K compliance and enhanced overall operational efficiency and business performance through BPCS upgrade—led migration to multiple Asia Pacific locations.",
      "Led the consolidation of five AS/400s locations to main AS/400 in Japan with migration of BPCS and various AS/400 applications; the consolidation provided cost savings in resources and security management.",
      "Implemented cutting-edge IT and Voice infrastructure for new building facilities for the Japan regional office and manufacturing facility.",
      "Established large, high-performance IT teams in the Japan regional office to support IT regional operations and support; utilized local resources in Japan to establish cost savings."
    ]
  }
dict3={
    "file": "Casey-Nakamura-System-Administrator-Resume (TechieCV.com).pdf",
    "name": "Casey Nakamura",
    "email": "sysadmin@gmail.com",
    "phone": "+1 3035-2222",
    "outcome": "scored",
    "score": 44.4,
    "reason": "Meets 1 of 3 rules. Missing: CCNA is listed as a certification; Has cloud experience (Ignored 1 claim(s) whose evidence did not pass the checks.)",
    "summary": "System Administrator with 8 years of experience in enterprise IT environments, specializing in Linux and Windows administration, virtualization, and security hardening. Strong in automation, monitoring, and networking.",
    "skills": [
      "RHEL",
      "Ubuntu",
      "CentOS",
      "Debian",
      "Windows Server 2019/2022",
      "VMware vSphere",
      "Hyper-V",
      "Proxmox",
      "KVM",
      "Docker",
      "Cisco IOS",
      "VLAN",
      "DNS",
      "DHCP",
      "VPN (IPSec, OpenVPN)",
      "pfSense",
      "Palo Alto firewalls",
      "CIS benchmarks",
      "CrowdStrike EDR",
      "Tenable",
      "MFA",
      "SOC 2",
      "ISO 27001",
      "Datadog",
      "Nagios",
      "Zabbix",
      "SolarWinds",
      "Veeam",
      "Commvault",
      "Ansible",
      "Puppet",
      "Chef",
      "PowerShell DSC",
      "Terraform",
      "Bash",
      "PowerShell",
      "Python",
      "Perl",
      "NetApp SAN",
      "Dell EMC",
      "NFS/SMB",
      "Active Directory",
      "Okta SSO",
      "LDAP"
    ],
    "qualifications": [
      "B.S. in Information Technology, University of Colorado Boulder, Sep 2014 - May 2018"
    ],
    "work_experience": [
      "Senior Systems Administrator, Lockheed Martin Space, Sep 2021 - Present",
      "Systems Administrator, Charter Communications, Jul 2018 - Aug 2021"
    ],
    "projects": [
      "Centralized monitoring on Datadog and Nagios for 600+ servers and 150+ services",
      "Enterprise backup and disaster recovery program on Veeam-based image backups and Commvault",
      "Incident response across 42 SEV1/SEV2 outages"
    ]
  }
resume1=Resume(dict1)
resume2=Resume(dict2)
resume3=Resume(dict3)
list1.list=[resume1,resume2,resume3]
print(list1.sort_score)
#print(list1.output_dict)
'''