PDRRMO Palawan Fleet Management System (FMS)

A Django-based Fleet Management System for the Provincial Disaster Risk Reduction and Management Office (PDRRMO) of Palawan, designed to support the management and organization of fleet-related information and maritime data.

Overview

The PDRRMO Palawan Fleet Management System is a web application developed using Python and Django. It provides a foundation for organizing fleet management records and supporting administrative workflows for disaster risk reduction and management operations in Palawan.

The project uses SQLite for database storage and includes Django applications for its system functionality.

Tech Stack
Backend: Python, Django
Database: SQLite
Admin Interface: Django Admin with Jazzmin
Excel Processing: OpenPyXL
PDF Generation: ReportLab
Timezone Support: tzdata
Features and Components

The repository includes the following components:

Fleet application — Django app for fleet-related functionality.
Django project configuration — Application settings, URL routing, and server configuration.
SQLite database — Local database for application data.
Maritime data population script — Script for populating maritime-related data.
Excel and PDF libraries — Dependencies available for spreadsheet processing and PDF generation.

Note: The components listed above are based on the repository structure and dependencies. Specific application features depend on the implemented source code.

Project Structure
PDRRMO_PalawanFMS/
├── fleet/                  # Fleet management application
├── pdrrmo_fleet/           # Django project configuration
├── db.sqlite3              # SQLite database
├── manage.py               # Django management utility
├── populate_maritime.py    # Maritime data population script
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
└── exit                    # Additional repository file

Prerequisites

Before installing the project, make sure you have the following:

Python 3.12 or a compatible version for the installed Django release
Git
pip (Python package installer)
A terminal or command prompt
Installation and Setup
1. Clone the repository
git clone https://github.com/jayrooKneel/PDRRMO_PalawanFMS.git


Navigate to the project directory:

cd PDRRMO_PalawanFMS

2. Create a virtual environment
python -m venv venv


Activate the virtual environment.

Windows (Command Prompt):

venv\Scripts\activate


Windows (PowerShell):

.\venv\Scripts\Activate.ps1


Linux or macOS:

source venv/bin/activate

3. Install dependencies

Install the packages listed in requirements.txt:

python -m pip install -r requirements.txt

4. Apply database migrations

Run the following commands to prepare the database schema:

python manage.py makemigrations
python manage.py migrate


If the project already has migrations and does not require new ones, running migrate is generally sufficient.

5. Create a superuser

Create an administrator account for accessing Django's administration interface:

python manage.py createsuperuser


Follow the prompts to configure the username, email address, and password.

6. Run the development server

Start the Django development server:

python manage.py runserver


Open the application in your browser:

Application: http://127.0.0.1:8000/
Django Admin: http://127.0.0.1:8000/admin/

The available pages depend on the project's configured URL routes.

Database

The project includes an SQLite database named db.sqlite3.

SQLite is suitable for local development and testing. Before deploying the application to a production environment, review the database configuration, backup procedures, access controls, and data protection requirements.

Avoid deleting or replacing the existing database unless you have confirmed that its contents are no longer needed.

Development Commands

Useful Django commands for development and maintenance:

Command	Purpose
python manage.py runserver	Start the development server
python manage.py check	Check the project configuration
python manage.py showmigrations	List migration status
python manage.py migrate	Apply database migrations
python manage.py createsuperuser	Create an administrator
python manage.py collectstatic	Collect static files when configured for deployment
Security and Deployment

Before deploying the system to a production server:

Set DEBUG = False.
Configure ALLOWED_HOSTS for the intended domain or server.
Store the Django secret key and other sensitive settings securely in environment variables.
Use HTTPS and appropriate authentication and authorization controls.
Back up the database and verify that restoration works.
Avoid committing passwords, secret keys, private records, or sensitive operational information to Git.
Review database and application access permissions before handling official fleet or maritime records.

The Django development server is intended for development and testing, not direct production use.

Contributing

Contributions and improvements are welcome.

Fork the repository.
Create a feature branch:
   git checkout -b feature/your-feature-name

Commit your changes:
   git add .
   git commit -m "Add your feature description"

Push your branch:
   git push origin feature/your-feature-name

Open a pull request for review.

Please test your changes and document any new setup requirements before submitting a contribution.

License

No license information has been specified in this README. Please consult the repository owner before redistributing or using this project beyond the permissions granted by the repository's applicable license.

Acknowledgments

Developed for the context of fleet management and disaster risk reduction and management operations in Palawan.

Repository: https://github.com/jayrooKneel/PDRRMO_PalawanFMS