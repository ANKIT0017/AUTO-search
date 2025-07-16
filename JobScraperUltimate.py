# Job Scraper Ultimate

## Settings

hours = 1  
sleep_time = 10  
scrape_from = ["linkedin", "indeed", "skillsire"]  
search_term = "machine learning engineer" 
results_fetch_count = 300 
country_to_search = 'India' 
file_name_prefix = '' 
roles_of_interest = [
    "DevOps", "Data Engineer","computer Vision Engineer", "NLP Engineer",
    "AI Researcher", "AI Scientist", "AI Specialist", "AI Developer",
    "Data Scientist", "Machine Learning Engineer", "AI Engineer",
    "Cloud Engineer","Data Analyst", "Data Architect", "Big Data Engineer",
    "Data Visualization",
]

#Email Settings
email_send = False  
from_email = ''
email_password = ''
to_email = ''
email_smtp = '' 


## Imports

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import time
import calendar
import csv
import os  # To check if the file exists
from jobspy import scrape_jobs
import pandas as pd
from datetime import datetime
import requests
import json
import argparse


## Helper Functions 


def getFileName(extraText):
    timeObj = time.localtime(time.time())
    
    time_of_day = ''
    
    if timeObj.tm_hour >= 0 and timeObj.tm_hour < 9: 
        time_of_day = 'overnight'
    elif timeObj.tm_hour >= 9 and timeObj.tm_hour < 12: 
        time_of_day = 'morning'
    elif timeObj.tm_hour >=12  and timeObj.tm_hour < 16: 
        time_of_day = 'afternoon'
    elif timeObj.tm_hour >= 16 and timeObj.tm_hour < 21: 
        time_of_day = 'evening'
    elif timeObj.tm_hour >= 21:
        time_of_day = 'night'
    
    file_name = 'jobs_'+calendar.month_name[timeObj.tm_mon]+'_'+str(timeObj.tm_mday)+'_'+time_of_day+'.csv'

    if len(extraText) > 0:
        file_name = extraText+'_'+file_name

    return file_name


# Function to get existing job URLs from the CSV file if it exists
def load_existing_jobs(file_name):
    if os.path.exists(file_name):
        # Skip comment lines and handle variable columns
        existing_jobs = pd.read_csv(
            file_name,
            quoting=csv.QUOTE_NONNUMERIC,
            escapechar="\\",
            comment='#'
        )
        if 'job_url' in existing_jobs.columns:
            return existing_jobs['job_url'].tolist()
        else:
            print(f"Warning: 'job_url' column not found in {file_name}. Deduplication skipped.")
            return []
    return []

## Emailer

def send_email(file_path, recipient_email):

    # Create the MIMEMultipart object
    message = MIMEMultipart()
    message['From'] = from_email
    message['To'] = to_email
    message['Subject'] = "Newly Scraped Job Listings"

    # Email body
    body = "Attached is the latest scrape of job listings."
    message.attach(MIMEText(body, 'plain'))

    # Attach the file
    attachment = open(file_path, "rb")
    part = MIMEBase('application', 'octet-stream')
    part.set_payload((attachment).read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', "attachment; filename= %s" % os.path.basename(file_path))
    message.attach(part)

    # Connect to the SMTP server and send the email
    server = smtplib.SMTP(email_smtp, 587)  # Use 465 for SSL
    server.starttls()  # Secure the connection
    server.login(from_email, email_password)
    text = message.as_string()
    server.sendmail(from_email, recipient_email, text)
    server.quit()

    print("Email sent successfully!")

## Skillsire Scraper

def construct_skillsire_job_url(job_id):
    return f"https://www.skillsire.com/job/jobs-enlisting/all-jobs?jobId={job_id}"

def fetch_jobs_from_skillsire(initial_payload):
    api_url = "https://www.skillsire.com/api/job/all-jobs"
    headers = {'Content-Type': 'application/json'}
    all_jobs = []  # List to hold all jobs
    offset = 0
    batch_size = 20  # Assume API returns jobs in batches of 20

    while True:
        # Update the payload with the current offset
        payload = initial_payload.copy()
        payload['offset'] = offset
        
        try:
            # Make the API call
            response = requests.post(api_url, data=json.dumps(payload), headers=headers)
            
            # Check if the request was successful
            if response.status_code == 200:
                data = response.json()
                jobs = data.get('jobs', [])
                all_jobs.extend(jobs)  
                
                total_jobs = data.get('metaData', {}).get('resultCount', 0) 
                total_jobs = total_jobs if total_jobs < results_fetch_count else results_fetch_count
                print(f"Fetched {len(jobs)} jobs (offset: {offset}), total so far from SkillSire: {len(all_jobs)} of {total_jobs}.")
                
                # If no more jobs are returned, we have fetched all available jobs
                if not jobs or len(all_jobs) >= total_jobs:
                    break

                # Update the offset for the next batch of jobs
                offset += batch_size
            else:
                print(f"Failed to fetch data. Status code: {response.status_code}")
                break
        except Exception as e:
            print(f"An error occurred: {e}")
            break

    return all_jobs

def skillSire_scraper(current_jobs):
    # Skillsire API details

    skillsire_hours_before = 'p'+ ('24' if hours > 1 else '1') + 'h'
    payload = {"loc":"India","cc":"in","type":"country","dp":skillsire_hours_before,"query":search_term}

    # Fetch jobs from Skillsire
    skillsire_jobs = fetch_jobs_from_skillsire(payload)
            
    if skillsire_jobs:
        # Convert Skillsire jobs into the structure expected in current_jobs
        skillsire_data = []
        for job in skillsire_jobs:
            
            job_location = "Unknown"  # Default location if not found
            if job.get('jobLocations') and len(job['jobLocations']) > 0:
                job_location = job['jobLocations'][0].get('jobState', "Unknown")
                
            job_data = {
                'job_url': construct_skillsire_job_url(job['jobId']),
                'title': job['jobTitle'],
                'company': job['jobCompany'],
                'location': job_location
            }
            skillsire_data.append(job_data)

        # Convert to DataFrame and append to current_jobs
        skillsire_df = pd.DataFrame(skillsire_data)
        current_jobs = pd.concat([current_jobs, skillsire_df], ignore_index=True)

    return current_jobs


roles_of_interest_lower = [role.lower() for role in roles_of_interest]
selected_fields = ['job_url', 'title', 'company', 'location']

include_skillsire = False

if "skillsire" in scrape_from:
    scrape_from.remove("skillsire")
    include_skillsire = True

# Load settings from JSON if available
SETTINGS_FILE = 'scraper_settings.json'
if os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
        _settings = json.load(f)
    hours = _settings.get('hours', hours)
    sleep_time = _settings.get('sleep_time', sleep_time)
    scrape_from = _settings.get('scrape_from', scrape_from)
    search_term = _settings.get('search_term', search_term)
    results_fetch_count = _settings.get('results_fetch_count', results_fetch_count)
    country_to_search = _settings.get('country_to_search', country_to_search)
    file_name_prefix = _settings.get('file_name_prefix', file_name_prefix)
    roles_of_interest = _settings.get('roles_of_interest', roles_of_interest)

# Parse command-line arguments for CSV file override
parser = argparse.ArgumentParser()
parser.add_argument('--csv', type=str, default=None)
args, unknown = parser.parse_known_args()

# Remove the while True loop and just run the scraping logic once
try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if hasattr(args, 'csv') and args.csv:
        file_name_csv = os.path.join(base_dir, args.csv)
    else:
        file_name_csv = os.path.join(base_dir, getFileName(file_name_prefix))
    timeObj = time.localtime(time.time())
    print(f"Starting scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # Scrape jobs from different platforms
    current_jobs = scrape_jobs(
        site_name=scrape_from, 
        search_term=search_term, 
        location="India",
        results_wanted=results_fetch_count,
        hours_old=hours,  
        country_indeed=country_to_search,
    )
    if include_skillsire:
        current_jobs = skillSire_scraper(current_jobs)
    current_jobs['title_lower'] = current_jobs['title'].str.lower()
    # Filter jobs based on matching roles
    matching_jobs = current_jobs[current_jobs['title_lower'].apply(
        lambda title: any(role in title for role in roles_of_interest_lower)
    )]
    matching_jobs = matching_jobs[selected_fields]
    # Load existing jobs from the CSV file (if it exists)
    existing_job_urls = load_existing_jobs(file_name_csv)
    # Perform set subtraction to find new jobs (using job_url)
    if existing_job_urls:
        new_jobs = matching_jobs[~matching_jobs['job_url'].isin(existing_job_urls)]
    else:
        new_jobs = matching_jobs
    job_count = len(new_jobs)
    if job_count > 0:
        # Add scrape_date and scrape_time columns to new_jobs
        scrape_date = time.strftime("%Y-%m-%d", timeObj)
        scrape_time = time.strftime("%H:%M:%S", timeObj)
        new_jobs = new_jobs.copy()
        new_jobs.loc[:, 'scrape_date'] = scrape_date
        new_jobs.loc[:, 'scrape_time'] = scrape_time
        # Save new jobs to a temp file for the web app
        new_jobs.reset_index(drop=True, inplace=True)
        with open(os.path.join(base_dir, 'new_jobs_temp.json'), 'w', encoding='utf-8') as f:
            f.write(new_jobs.to_json(orient='records', force_ascii=False))
        # Write a comment line as a separator
        with open(file_name_csv, 'a', encoding='utf-8') as f:
            f.write(f'# Jobs Scraped at : , #, {scrape_date}, {scrape_time}\n')
        # Only append new jobs (no dummy row)
        file_exists = os.path.exists(file_name_csv)
        with open(file_name_csv, 'a', newline='', encoding='utf-8') as csv_file:
            new_jobs.to_csv(
                csv_file, 
                header=not file_exists,  # Add header only if file doesn't exist
                quoting=csv.QUOTE_NONNUMERIC, 
                escapechar="\\", 
                index=False
            )
        if email_send:
            time.sleep(10) #This is set because the CSV Takes time to save
            send_email(file_name_csv,to_email)
    print("Scraping run complete.")
except KeyboardInterrupt:
    print("Scraping stopped by user.")









