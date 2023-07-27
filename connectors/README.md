# Twilio Voicemails

Lifecycle for first-time users
* User calls our number
* Voxana briefly greats (TODO: this should depend on past experience)
* User records voicemail
* Hangs up (or presses #)
* Uploads the recording S3 (using iam *user* `twilio-funcions-user` with AWS Access Key)
  * These credentials are set in Twilio Function Environment Variables
* That S3 upload triggers the main voice processing Lambda
  * It also onboards the phone number (along with full name and other metadata)
* We send a sms depending on:
  * New account: Request email to send drafts
  * Existing account, success: Send confirmation
  * Existing account, error: send notification
  * A careful reader might notice the case that results might be processed before we have an email
    * We should send a SMS reminder
    * Upon email update, send all "pending" drafts (we will have to support "queued" email_log)
* For the email input response:
  * Twilio function takes it, calls AWS API Gateway `POST sms/set-email` with credentials
  * Best effort parses the email address and verifies correctness
  * Updates the Account.Onboarding.email