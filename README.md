# RegVil

**RegVil** is a ann app that uses Altinn.no APIs to recieve and deliver forms regarding the digitalisation strategy in Norway.

## Architecture Overview

RegVil is built in **Python** (Flask) and consists of several modules:
- `app.py`: Main web-service / API layer  
- `clients/`: Contains Altinn API client logic  
- `config/`: Configuration (e.g., settings, secrets)  
- `data/`: Test data, same structure as the unse used for this project
- `tests/`: Test suite  
- Utility scripts:
  - `send_warning.py`, `send_reminders.py`, etc.: for background tasks  
  - `upload_skjema.py`: for submitting Altinn forms  
  - `delete_instance.py`: for cleaning up test or real instances  

Dockerfile is provided for containerization.

## How It Works
1. An initial form is sent by running `upload_skjema.py` locally. The file accesses the corresponding file with the recipients and prefill information from a Storage Blob. It generates a log in that same blob with the information sent.
2. An initial notification is sent by running `send_initiell_warning.py`. This uses the same recipients file as before. It also generates a log in the blob for the notification sent.
3. When a form is submitted Altinn Events API sends a callback to `app.py` that, if successful, would trigger `get_initiell_skjema.py`.
4. `get_initiell_skjema.py` will download the information submitted in the form into a log file. It will then trigger `upload_single_skjema.py` with the appropriate information for the new form to the sent, including form name and timepoint to be recieved.
5. After the new form is sent `app.py` will trigger `send_warning.py` to insatansiate a notification that will arrive at the same timepoint as the form.



## Altinn API Integration

RegVil uses several Altinn API .
- **Altinn App API**: Instances GET and POST for sharing the forms data.
- **Altinn Events API**: Subscription towards our app for getting the callback when a form is submitted.
- **Altinn Varslinger API**: Order POST to send a notification, PUT to cancel it. Also Status GET to check if the notification was recieved. 
