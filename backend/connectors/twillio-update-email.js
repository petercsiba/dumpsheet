const axios = require('axios');

exports.handler = async function(context, event, callback) {
    const url = 'https://api.voxana.ai/call/set-email';
    const apiKey = context.AWS_UPDATE_EMAIL_API_KEY;

    try {
        const response = await axios({
            method: 'post',
            url: url,
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json'
            },
            data: {
                phone_number: event.From,  // the phone number of the sender
                message: event.Body,  // the entire SMS body
            }
        });

        console.log(response.data);
        callback(null, response.data);
    } catch (error) {
        console.error(error);
        callback(error);
    }
};
