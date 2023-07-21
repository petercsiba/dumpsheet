# sam_app

This project contains source code and supporting files for a serverless application that you can deploy with the SAM CLI. It includes the following files and folders.

# Context
- high-level decisioning: https://chat.openai.com/share/e42961e1-b060-447b-824f-ff6a47f6c0e1
- - As I later learned, there are a [TON of publicly available functions](https://us-east-1.console.aws.amazon.com/serverlessrepo/home?region=us-east-1#/available-applications) (like ffmpeg translator on alpine)
- more details, especially around python imports (TLDR, must be self-contained-ish) https://chat.openai.com/share/18c9d98c-83d7-495e-8f55-a46955508edc

## Structure
- events - Invocation events that you can use to invoke the function.
- tests - Unit tests for the application code.
- template.yaml - A template that defines the application's AWS resources.
- other directories - one per lambda function

The application uses several AWS resources, including Lambda functions and an API Gateway API.
These resources are defined in the `template.yaml` file in this project. Y
If you prefer to use an integrated development environment (IDE) to build and test your application, you can use the AWS Toolkit.
The AWS Toolkit is an open source plug-in for popular IDEs that uses the SAM CLI to build and deploy serverless applications on AWS. The AWS Toolkit also adds a simplified step-through debugging experience for Lambda function code. See the following links to get started.
* [PyCharm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)

# Development

## Debugging
These chains of calls and dependencies are tougher than it seems:
* FE from app.voxana.ai calls api.voxana.ai
* * You can track request / response headers in Chrome Debug tools (don't trust console logs that much)
* * Double-check `curl -X <method> https://api.voxana.ai/...` as browsers require CORS. Trust this response more.
* Hits the AWS API Gateway - these get logged into `API-Gateway-Execution-Logs_99bfn3hfh5/Prod`
* Then it calls a Lambda
* Responds back

### CORS
https://stackoverflow.com/questions/38987256/aws-api-gateway-cors-post-not-working
While on the FE errors *can* propagate as CORS problems

## Deploy the sample application

The Serverless Application Model Command Line Interface (SAM CLI) is an extension of the AWS CLI that adds functionality for building and testing Lambda applications. It uses Docker to run your functions in an Amazon Linux environment that matches Lambda. It can also emulate your application's build environment and API.

To set up the SAM CLI, refer to the main README: https://github.com/voxana-ai/backend

To build and deploy your application for the first time, run the following in your shell:

```bash
# to double-check
sam build --use-container
# if not already, start url  https://d-90679cf568.awsapps.com/start/
aws configure sso
# for new IAM roles, you would need AdminAccess
sam deploy --profile PowerUserAccess-831154875375
```

## Use the SAM CLI to build and test locally

Build your application with the `sam build --use-container` command.

```bash
sam_app$ sam build --use-container
```

The SAM CLI installs dependencies defined in `hello_world/requirements.txt`, creates a deployment package, and saves it in the `.aws-sam/build` folder.

Test a single function by invoking it directly with a test event. An event is a JSON document that represents the input that the function receives from the event source. Test events are included in the `events` folder in this project.

Run functions locally and invoke them with the `sam local invoke` command.

```bash
sam_app$ sam local invoke HelloWorldFunction --event events/event.json
```

The SAM CLI can also emulate your application's API. Use the `sam local start-api` to run the API locally on port 3000.

```bash
sam_app$ sam local start-api
sam_app$ curl http://localhost:3000/
```

The SAM CLI reads the application template to determine the API's routes and the functions that they invoke. The `Events` property on each function's definition includes the route and method for each path.

```yaml
      Events:
        HelloWorld:
          Type: Api
          Properties:
            Path: /hello
            Method: get
```

## Add a resource to your application
The application template uses AWS Serverless Application Model (AWS SAM) to define application resources. AWS SAM is an extension of AWS CloudFormation with a simpler syntax for configuring common serverless application resources such as functions, triggers, and APIs. For resources not included in [the SAM specification](https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md), you can use standard [AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) resource types.

## Fetch, tail, and filter Lambda function logs

To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
sam_app$ sam logs -n HelloWorldFunction --stack-name "sam_app" --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).

## Tests

Tests are defined in the `tests` folder in this project. Use PIP to install the test dependencies and run tests.

```bash
sam_app$ pip install -r tests/requirements.txt --user
# unit test
sam_app$ python -m pytest tests/unit -v
# integration test, requiring deploying the stack first.
# Create the env variable AWS_SAM_STACK_NAME with the name of the stack we are testing
sam_app$ AWS_SAM_STACK_NAME="sam_app" python -m pytest tests/integration -v
```

## Cleanup

To delete the sample application that you created, use the AWS CLI. Assuming you used your project name for the stack name, you can run the following:

```bash
sam delete --stack-name "sam_app"
```

## Resources

See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to SAM specification, the SAM CLI, and serverless application concepts.

Next, you can use AWS Serverless Application Repository to deploy ready to use Apps that go beyond hello world samples and learn how authors developed their applications: [AWS Serverless Application Repository main page](https://aws.amazon.com/serverless/serverlessrepo/)
