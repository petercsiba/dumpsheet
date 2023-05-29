import json

data = {
    'Records': [
        {
            'eventSource': 'aws:ses',
            'eventVersion': '1.0',
            'ses': {
                'mail': {
                    'timestamp': '2023-05-29T02:31:02.064Z',
                    'source': 'petherz@gmail.com',
                    'messageId': 'eum0bdo222snm080shoh3oreg5gd8fldgdrebmo1',
                    'destination': ['test@katka.ai'],
                    'headersTruncated': False,
                    'headers': [
                        {'name': 'Return-Path', 'value': '<petherz@gmail.com>'},
                        {'name': 'Received', 'value': 'from mail-wm1-f52.google.com (mail-wm1-f52.google.com [209.85.128.52]) by inbound-smtp.us-west-2.amazonaws.com with SMTP id eum0bdo222snm080shoh3oreg5gd8fldgdrebmo1 for test@katka.ai; Mon, 29 May 2023 02:31:02 +0000 (UTC)'},
                        {'name': 'X-SES-Spam-Verdict', 'value': 'PASS'},
                        {'name': 'X-SES-Virus-Verdict', 'value': 'PASS'},
                        {'name': 'Received-SPF', 'value': 'pass (spfCheck: domain of _spf.google.com designates 209.85.128.52 as permitted sender) client-ip=209.85.128.52; envelope-from=petherz@gmail.com; helo=mail-wm1-f52.google.com;'},
                        {'name': 'Authentication-Results', 'value': 'amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates 209.85.128.52 as permitted sender) client-ip=209.85.128.52; envelope-from=petherz@gmail.com; helo=mail-wm1-f52.google.com; dkim=pass header.i=@gmail.com; dmarc=pass header.from=gmail.com;'},
                        {'name': 'X-SES-RECEIPT', 'value': 'AEFBQUFBQUFBQUFFRS9Wd053blh1WTJ4dDV1eG9VclAxTE55dzIzNHh5V0QzcUVYS3pvRk1vbEZ4anVCcys1Uk9TVVB3SUxOWUhZbzhtQS9sZEVIbXlkOEZiRkdXbEhuaVlkb2VSbXFERUtOcGJyVStEWHc2SkNIRGk0WjcxbURuUFFvbzNBWUZiWCtvMlhjR2UzUHVkMDYyRTQweGZCbllGSzRkR0tlMWhCRmlyZ3BmNUNKVDV2dW9VSU40UUk5emtkYUw1NmNRVjd6cEZIWEZOR3BjSGJER0NlRmlwWEhsQmFoUklKcy95eEtOQ0QwYnliY3k5WU1UVzRZK0pDbW1sQy8yQXRTdnlUcmJUaXZ4R1BWVzhnbVJhM3hwK282QUhuOXlsYktvT2xHZlJ6enRsRjVNV2c9PQ=='},
                        {'name': 'X-SES-DKIM-SIGNATURE', 'value': 'a=rsa-sha256; q=dns/txt; b=OQoFdd8/2bZWmABXW4SltM+VUntyNWkjJuoaZ0fLgcj7jmLnc8CTrE9t7GysnnH3v4VRNW84Z6E+DxwTlRV6evvyu5qG0x81PFEgCfZdG0TW4P9tVQihE99/YOvVkmnyrEfM059zPPuqzp0tuMfhVaXgvOnD2+kRXHFBflfWT2M=; c=relaxed/simple; s=hsbnp7p3ensaochzwyq5wwmceodymuwv; d=amazonses.com; t=1685327463; v=1; bh=pRY6WjdFPnsYz3lxToTqOGoeFCXTRI8U+f7CZrSJakM=; h=From:To:Cc:Bcc:Subject:Date:Message-ID:MIME-Version:Content-Type:X-SES-RECEIPT;'},
                        {'name': 'Received', 'value': 'by mail-wm1-f52.google.com with SMTP id 5b1f17b1804b1-3f603ff9c02so17959545e9.2 for <test@katka.ai>; Sun, 28 May 2023 19:31:01 -0700 (PDT)'},
                        {'name': 'DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=gmail.com; s=20221208; t=1685327459; x=1687919459; h=to:subject:message-id:date:from:mime-version:from:to:cc:subject:date:message-id:reply-to; bh=sWDEhhImHCglsokZA6rsuPVWyUIku4XjLITG8JcsJlM=; b=fpFe5HSyJt9Dp4kzXQGtURtCnbFMtsovXBLyflnrBlwhyG2/qIj9Vmn/fAykgJrk94eKZsjL4HE1Le09NnCITZBYNyGpk35LIFaaxY5BfYibqk8xyUt/Ot+g75senr0XkvhALIPUgO9L4A8c4mgKvL/Ufe82rUVz7je12hcyKA82AINuKFVyVMiHVQwyuRiwYg1mBLzyw/yMAK5j/CkHanvwqAYl4UQq8VunPHLjChisB8/jjDneQA3QzAJ5x0SxDEFnw3IdZOiQBb7U86bRKUJTcUqxbv0QEmRemsP2TbkT3auFNPRirOxHeheONvkfAk/QQs3ESLBWtmCGNnEJDA=='},
                        {'name': 'X-Google-DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20221208; t=1685327459; x=1687919459; h=to:subject:message-id:date:from:mime-version:x-gm-message-state :from:to:cc:subject:date:message-id:reply-to; bh=sWDEhhImHCglsokZA6rsuPVWyUIku4XjLITG8JcsJlM=; b=boqLnOrbV0tgWLaeRX0nYpHaNLx7Uv6fKgImX7FMFShtH7pdk40e/fNPray5NGRNF2 73Zp5L6YOYBBCnzWD25b7VbUq8hzjsoQS6wwUciESdgv1Yxz+TgcGQ+e4x2ftJ/EIRMF DDROT7lRRPQzoPy9fYieJXXa02mj/kMr/8LBCAaBabq62ZZhwAEWVdTlf3wCPy/Vkk7o rnszd5M3KscZ6Vn6S57MI/m729E2njJOZr5ZpLz3rxcIyAllxAQ5cWPITlrsgTSgRvsp 2sex2oh7yDInkoczRZit2PBO0dfHHwJT3NVVLNlDGV56czVGf7fS+SuUJZbnAlWjvTW/ 9d+w=='},
                        {'name': 'X-Gm-Message-State', 'value': 'AC+VfDx7IveDDaTSbJjd4lLmNYWrlnecyR6eE6Y8ddmA1eczODnEJps8 bbgmcv1+ipuzq3oObm9oW7B8bTCwouGHN+P4tHefZ+Q6Q58='},
                        {'name': 'X-Google-Smtp-Source', 'value': 'ACHHUZ50E+f1ZF9fX9ohYxqvBTZUchQs5I4bqccHly4t3w34Dlcz82eVIgUzAZT8vBJWPAvHF8cTLAjGIVKlhoIeTCI='},
                        {'name': 'X-Received', 'value': 'by 2002:a5d:6891:0:b0:309:4ab7:c94 with SMTP id h17-20020a5d6891000000b003094ab70c94mr8230383wru.59.1685327458785; Sun, 28 May 2023 19:30:58 -0700 (PDT)'},
                        {'name': 'MIME-Version', 'value': '1.0'},
                        {'name': 'From', 'value': 'Peter Csiba <petherz@gmail.com>'},
                        {'name': 'Date', 'value': 'Sun, 28 May 2023 19:30:47 -0700'},
                        {'name': 'Message-ID', 'value': '<CAAVtfSWZsJTmvTj-59ssir8-eb1HKbjQXDjXfsbfco5bbHYv-g@mail.gmail.com>'},
                        {'name': 'Subject', 'value': 'Test 2'},
                        {'name': 'To', 'value': 'test@katka.ai'},
                        {'name': 'Content-Type', 'value': 'multipart/mixed; boundary="00000000000082f80305fccbe0f3"'}
                    ],
                    'commonHeaders': {
                        'returnPath': 'petherz@gmail.com',
                        'from': ['Peter Csiba <petherz@gmail.com>'],
                        'date': 'Sun, 28 May 2023 19:30:47 -0700',
                        'to': ['test@katka.ai'],
                        'messageId': '<CAAVtfSWZsJTmvTj-59ssir8-eb1HKbjQXDjXfsbfco5bbHYv-g@mail.gmail.com>',
                        'subject': 'Test 2'
                    }
                },
                'receipt': {
                    'timestamp': '2023-05-29T02:31:02.064Z',
                    'processingTimeMillis': 1875,
                    'recipients': ['test@katka.ai'],
                    'spamVerdict': {'status': 'PASS'},
                    'virusVerdict': {'status': 'PASS'},
                    'spfVerdict': {'status': 'PASS'},
                    'dkimVerdict': {'status': 'PASS'},
                    'dmarcVerdict': {'status': 'PASS'},
                    'action': {
                        'type': 'Lambda',
                        'functionArn': 'arn:aws:lambda:us-west-2:680516425449:function:test-email-receipt',
                        'invocationType': 'RequestResponse'
                    }
                }
            }
        }
    ]
}

json_data = json.dumps(data)
print(json_data)