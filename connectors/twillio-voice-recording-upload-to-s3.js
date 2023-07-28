const AWS = require('aws-sdk');
const axios = require('axios');
const s3 = new AWS.S3();
// lodash is a default dependency for deployed Functions, so it can be imported
// with no changes on your end
const { startCase } = require('lodash');

exports.handler = async function(context, event, callback) {
    // The pre-initialized Twilio Client is available from the `context` object
    const client = context.getTwilioClient();
    // Create a new voice response object
    const twiml = new Twilio.twiml.VoiceResponse();

    try {
        // Get the URL of the recording
        let recordingUrl = event.RecordingUrl;

        // Verify if the recordingUrl is valid
        if (!recordingUrl || !recordingUrl.startsWith('http')) {
            console.log('Invalid RecordingUrl:', recordingUrl);

            // Try to get the MediaUrl
            recordingUrl = event.MediaUrl;
            console.log('Using MediaUrl instead:', recordingUrl);
        }

        console.log('Downloading recording from URL:', recordingUrl);

        // Download the recording
        const response = await axios.get(recordingUrl, { responseType: 'arraybuffer' });
        const recording = response.data;

        // Get the phone number of the caller
        var phoneNumber = event.From;  // undefined for recording events
        const callSid = event.CallSid;
        try {
            // Note the use of async await here
            const call = await client.calls(callSid).fetch();
            phoneNumber = call.from;
        } catch (err) {
            console.log(err);
        }
        console.log('Parsed phone number:', phoneNumber);

        var carrierInfo = ""
        var properName = ""
        // Also attempt to get their name
        // NOTE: This is a paid feature
        try {
            const lookupResult = await client.lookups.phoneNumbers(phoneNumber)
                .fetch({ type: ['carrier', 'caller-name'] });

            console.log('Carrier name: ', lookupResult.carrier.name);
            // 'Carrier name: AT&T'
            console.log('Carrier type: ', lookupResult.carrier.type);
            // 'Carrier type: mobile'
            console.log('Caller name: ', lookupResult.callerName.caller_name);
            // 'Caller name: DOE,JOHN'
            console.log('Caller type: ', lookupResult.callerName.caller_type);
            // Caller type: CONSUMER'

            if (lookupResult.callerName.caller_name) {
                // Attempt to nicely format the users name in a response, if it exists
                const [lastName, firstName] = lookupResult.callerName.caller_name
                    .toLowerCase()
                    .split(',');
                properName = startCase(`${firstName} ${lastName}`);
            }
            carrierInfo = `${lookupResult.carrier.name} ${lookupResult.callerName.caller_type} ${lookupResult.carrier.type}`
        } catch (error) {
            // Just use default properName
            console.error('could not get properName cause:', error);
        }
        console.log('Parsed proper name:', properName);

      // Upload the recording to S3
        const params = {
            Bucket: 'requests-from-twilio',
            Key: `${callSid}.wav`, // use the call SID as the file name
            Body: recording,
            ContentType: 'audio/wav',
            Metadata: {
                'callSid': String(callSid),
                'phoneNumber': String(phoneNumber),
                'properName': String(properName),
                'carrierInfo': String(carrierInfo)
            }
        };
        await s3.putObject(params).promise();

        // End the function
        // TODO: update with Twiml stuff
        // https://www.twilio.com/docs/serverless/functions-assets/quickstart/lookup-carrier-and-caller-info
        // If we don't have a name, fallback to reference the carrier instead
        // Rather play a voice recording, as Twillio default voices quite suck
        // https://beta.elevenlabs.io/speech-synthesis
        twiml.say(`Thank you ${properName}!`);
        callback(null, twiml);
    } catch (error) {
        console.error(error);
        callback(error, null);
    }
};