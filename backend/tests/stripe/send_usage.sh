#!/bin/bash

CUSTOMER_ID="cus_QknqH2jyRZpsmP"

curl https://api.stripe.com/v1/billing/meter_events \
	-u "sk_test_51PtHu91km7GQ4a4TW7gCTpq56LoXHvO4jmD2H7P8Z9s1oRxFnnuxDBXcxf5aem4APT4GsegqklQtVTo6C4BmcUR800voUQOCgL:" \
	-d event_name=open_ai_cost \
	-d timestamp=$(date +%s) \
	-d "payload[stripe_customer_id]"="$CUSTOMER_ID" \
	-d "payload[value]"=1
