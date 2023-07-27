// https://console.twilio.com/us1/develop/functions/editor/ZS2535c1c4daf9e8fb7c867f339a2210a7/environment/ZE0a803b664e81b223cbd8289f10ca0ffb/function/ZHdb777c33e70dc8c7babaaeacef46b928
const axios = require('axios');

exports.handler = async function(context, event, callback) {
    const url = 'https://k4qviavjh1.execute-api.us-west-2.amazonaws.com/prod/user';
    const apiKey = context.AWS_UPDATE_EMAIL_API_KEY;

    try {
        const response = await axios({
            method: 'put',
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
