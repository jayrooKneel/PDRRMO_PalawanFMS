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

Deployment location searches use a locally bundled, filtered copy of the [Philippines Administrative Divisions dataset](https://github.com/open-admin-data/philippines-administrative-divisions), limited to Puerto Princesa City and barangays in Palawan. Location selections are validated by the server as well as the browser. The data is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the source and filtering changes are attributed in the deployment forms and location data file.

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

The logistics asset form uses local Tesseract OCR to read LTO OR/CR and MARINA document images. On Windows, install Tesseract with the English language data from the [UB Mannheim Windows installer](https://github.com/UB-Mannheim/tesseract/wiki). Django auto-detects `tesseract` on `PATH` or the default `C:\Program Files\Tesseract-OCR\tesseract.exe` location; set `TESSERACT_CMD` if installed elsewhere. Restart the Django server after installation. Confirm the installation with `tesseract --version` and `tesseract --list-langs` (which should include `eng`). Images are processed by the application server and are not sent to a cloud OCR provider. OCR suggestions exclude registered-owner names and addresses; review every suggested field before saving.

Land asset details follow the LTO Form 3 registration fields, including vehicle category, engine and chassis numbers, MV file number, passenger capacity, color, fuel, classification, make/series, gross and net weight, body style, model year, piston displacement, and air-conditioning type. The fleet asset type is selected first, separately from the LTO vehicle category.

The logistics driver form can also scan LTO driver-license or MARINA license/certificate images. It suggests only the driver's name, license/certificate number, license codes or seafarer rank, and expiry date. Date of birth and address are not extracted, phone number remains manual, and uploaded images are discarded after OCR instead of being stored.

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

### Mobile and installable app

The fleet pages include responsive layouts for phone and tablet screens and can be installed as a Progressive Web App (PWA). Open the application in a supported browser and choose **Install app** when prompted (or use the browser's install option). The service worker caches only the app's static shell; sign-in and fleet records still require a network connection. PWA installation requires HTTPS in production; `localhost` and `127.0.0.1` are treated as secure for local development.

Database

The project includes an SQLite database named `db.sqlite3` for local development. The production deployment below uses PostgreSQL; it does not use or overwrite the local SQLite file.

Avoid deleting or replacing the existing database unless you have confirmed that its contents are no longer needed.

Production Deployment (Render + PostgreSQL)
-------------------------------------------

This guide deploys the Django application to a Render Web Service and stores production records in a Render PostgreSQL database. The current checked-in settings are development settings (SQLite, `DEBUG=True`, and a literal secret key), and the requirements do not yet include a production web server, PostgreSQL driver, database URL parser, or static-file middleware. Complete the preparation below before connecting a public service. These are deployment steps; they do not change the local development setup.

### 1. Prepare production settings and dependencies

Add these packages to `requirements.txt` and commit the updated file:

```text
dj-database-url
gunicorn
psycopg[binary]
whitenoise
```

In `pdrrmo_fleet/settings.py`, replace the development `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and SQLite `DATABASES` definitions with environment-driven settings. Add the imports shown here:

```python
import os
import dj_database_url
```

Use the following production configuration (keep the rest of the existing settings):

```python
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=600,
        ssl_require=True,
    )
}
```

For static files, add `whitenoise.middleware.WhiteNoiseMiddleware` immediately after `django.middleware.security.SecurityMiddleware` in `MIDDLEWARE`, then configure:

```python
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

For HTTPS behind Render's proxy, also set:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

The database URL must be a PostgreSQL URL provided by Render, not a URL committed to source control. Keep `DJANGO_DEBUG` false in production. Set `DJANGO_ALLOWED_HOSTS` to the exact Render hostname (and any custom domain), without a scheme; set `CSRF_TRUSTED_ORIGINS` to the corresponding `https://` origins.

### 2. Create the Render PostgreSQL database

1. In the Render Dashboard, create a PostgreSQL database in the region you will use for the web service. Choose a plan and retention period suitable for the sensitivity, availability, and backup requirements of official fleet records.
2. Copy the database's **Internal Database URL** from its connection details. Use the internal URL when the web service and database are in the same Render region. Do not publish, commit, or share database URLs or credentials.
3. Keep the database's backups and retention settings enabled according to your organization's recovery policy. Test restoring a backup before relying on it.

### 3. Create and configure the web service

1. Push the prepared application to a GitHub repository accessible to Render, then create a Render **Web Service** from that repository. Select the branch to deploy and a Python runtime supported by the pinned Django version.
2. Set the build command to:

   ```sh
   pip install -r requirements.txt && python manage.py collectstatic --no-input
   ```

3. Set the start command to:

   ```sh
   python -m gunicorn pdrrmo_fleet.wsgi:application --bind 0.0.0.0:$PORT
   ```

4. In the service's **Environment** settings, add:
   - `DATABASE_URL`: the PostgreSQL **Internal Database URL** from step 2.
   - `DJANGO_SECRET_KEY`: a newly generated, private production secret key. Do not reuse the development key or commit the value.
   - `DJANGO_DEBUG`: `False`.
   - `DJANGO_ALLOWED_HOSTS`: the service hostname, for example `your-service.onrender.com`; add a custom hostname as needed, separated by commas.
   - `CSRF_TRUSTED_ORIGINS`: for example `https://your-service.onrender.com`; add each custom HTTPS origin as needed, separated by commas.
5. Save the settings and deploy. Use Render's environment-variable UI or secret management; never put credential values in the repository or deployment logs.

### 4. Initialize the production database

Before directing users to the new service, open a Render Shell for the web service and run:

```sh
python manage.py check --deploy
python manage.py migrate --noinput
python manage.py createsuperuser
```

Run migrations once for the target database, before serving production traffic. Do not run `makemigrations` on the hosting service: generate and review migrations in development, commit them, and apply them to production with `migrate`. For later releases, apply pending migrations as a controlled deployment step before the new application code needs them; avoid running migrations concurrently from multiple web workers.

Verify the service health, sign in through the configured login page, test static assets and essential workflows, and check that records persist after a new deployment. Configure a custom domain and HTTPS in Render before sharing the site.

### 5. Move existing local data, if required

The Render database starts separately from `db.sqlite3`. Do not copy or rename the SQLite file to use it as PostgreSQL. If local fleet records must be carried over, first take and retain a tested backup of both databases, freeze writes during the transfer, and test the process against a staging database. Django can export and import application data:

```sh
# On the source environment, after backing up db.sqlite3:
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 > fleet-data.json

# On the target environment, after deploying code and applying migrations:
python manage.py loaddata fleet-data.json
```

Transfer the export through a protected channel, restrict access to it, and remove temporary copies when the migration is verified. This is a data transfer, not a substitute for validating relationships, user access, audit history, record counts, and application behavior. Plan a controlled cutover; do not allow users to write independently to both databases.

### Enterprise PostgreSQL and operations

If PostgreSQL is hosted by your organization instead of Render, have the database administrator provision a production database and a dedicated least-privilege application role. Set `DATABASE_URL` to the approved PostgreSQL connection URL in Render's environment settings. Confirm the hosting service can reach the database over an approved private network or allowlisted route, and require TLS as directed by the DBA. Never expose a database port publicly just to make the connection work. Confirm connection limits, maintenance windows, backup/restore ownership, retention, recovery objectives, monitoring, and incident contacts with the organization before launch.

The Render and database dashboards can change; consult the current [Render Django deployment guide](https://render.com/docs/deploy-django), [Render PostgreSQL connection guide](https://render.com/docs/postgresql-creating-connecting), and [Django deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/) while preparing production.

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

Before going live, review Django's deployment checklist, enforce HTTPS and appropriate authentication and authorization controls, back up the database and verify restoration, and review database and application access permissions before handling official fleet or maritime records. Avoid committing passwords, secret keys, private records, or sensitive operational information to Git.

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
