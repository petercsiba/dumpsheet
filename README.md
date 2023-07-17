## Local Setup
Setup Python your preferred way (virtualenv recommended) just ask GPT that `pyenv create virtualenv`


### Run tests
For now, most of the Python files have a `if __name__ == "__main__":` which essentially runs a test.
So you can test the lambda logic by:
```bash
# inside the backend/ directory
pyenv virtualenv 3.9.16 backend
# you might need to run `source ~/.bash_profile` for the new PYENV settings
pyenv activate backend  # just making sure
python -m app.app
```
TLDR; The `backend` project is now installed as a module through `setup.py`, so we can conclude research like:
```bash
python -m research.action_based_transition
```

### Setup DynamoDB Local (GPT generated)
* Requires JAVA, verify with `java -version`
* Download (DynamoDB Tar)[https://s3.us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.tar.gz]
* OR just `curl -O https://dynamodb-local.s3.us-west-2.amazonaws.com/dynamodb_local_latest.tar.gz
`
* Unpack `tar -xvf dynamodb_local_latest.tar`
* `app/app.py` starts it itself, if you need it you can start it with (default port is 8000): `java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb`

### Setup Other Requirements
* ffmpeg
* colima

### Running the Lambda locally
This is tricky for our case as it's triggered by an email stored in S3,
so prefer `python -m app.app`.
```shell
docker build -t hello-world .
docker run -p 9000:8080 hello-world
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```


## Deployment

### Set up AWS config
```shell
aws configure sso --profile voxana-prod
```
More in https://www.notion.so/AWS-83f07c0ce85d4e2f8cffbc1bf3a8d700?pvs=4#f9c71df32f024c758e523ca99980dd72

### Push New Image
Yeah hardcoded stuff - but it works!
```shell
aws ecr get-login-password --region us-east-1 --profile voxana-prod | docker login --username AWS --password-stdin 831154875375.dkr.ecr.us-east-1.amazonaws.com
docker build -t 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups .
docker push 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups:latest
```

### Deploy Lambda
A few manual clicks in AWS console:
* Go to Lambda
* Click on deploy new image
* Click through to find the newest
* You can re-run it by re-uploading to S3 some of the previous files.

# Oncall
* Usage https://platform.openai.com/account/usage

# Tough problems with setup

### Runing x86_64 (i.e. amd64) containers locally on M1/M2
The core problem is that some tools force our base image for deployment, e.g.:
* AWS Lambda only supports non-mainstream Linux (either python-alpine or amazon-linux)
* `chromedriver` requires Ubuntu or Debian (learned the hard way see `fails/`)

BUT you can NOT build / run across architectures, i.e. if you have M2 (`arm`)
and your target image is `amd` then you will get weird failures.

Obviously, Docker should make this easier.
I personally use `colima` over Docker Desktop (which kills battery)
For `colima` you need to install Docker `buildx` manually:
```shell
ARCH=arm64 # change to 'amd64' for non M[12]
VERSION=v0.10.4
curl -LO https://github.com/docker/buildx/releases/download/${VERSION}/buildx-${VERSION}.darwin-${ARCH}
mkdir -p ~/.docker/cli-plugins
mv buildx-${VERSION}.darwin-${ARCH} ~/.docker/cli-plugins/docker-buildx
chmod +x ~/.docker/cli-plugins/docker-buildx
docker buildx version # verify installation
```
https://dev.to/maxtacu/cross-platform-container-images-with-buildx-and-colima-4ibj

NOTE: Apply out of box for backwards compatibility supports `arch -x86_64`,
which runs code on the previous architecture.

Now you can build images for multiple platforms at once, wowz amaze:
```shell
docker buildx build --platform linux/arm64 -t chrome_webscraper chrome_webscraper/ --load
# If you're building an image for multiple platforms using the --platform
# flag with more than one target platform, you should use --push flag instead of --load
# to push the resulting multi-platform image to a Docker registry.
docker buildx build --platform linux/amd64,linux/arm64 -t chrome_webscraper chrome_webscraper/ --push
```

Running them is a different story, I couldn't figure it out so I just have workarounds :/
For:
* `chromedriver`, just download arm64 version https://sites.google.com/chromium.org/driver/downloads
* copy to `/usr/local/bin/chromedriver`
* when first run, Apple will freak out, go to Mac Settings -> Privacy & Security -> Security Settings
* click allow
* run again

```shell
 => [linux/amd64  3/10] RUN apt-get update     && apt-get install -y --no-install-recommends     wget     curl     unzip
 => => # Preparing to unpack .../07-ucf_3.0038+nmu1_all.deb ...
 => => # Moving old data out of the way
 => => # Unpacking ucf (3.0038+nmu1) ...
 => => # Selecting previously unselected package libpcre2-8-0:amd64.
 => => # Preparing to unpack .../08-libpcre2-8-0_10.32-5+deb10u1_amd64.deb ...
 => => # Unpacking libpcre2-8-0:amd64 (10.32-5+deb10u1) ...
 => [linux/arm64  4/10] RUN apt-get update && apt-get install -y chromium
 => => # Preparing to unpack .../029-libcroco3_0.6.12-3_arm64.deb ...
 => => # Unpacking libcroco3:arm64 (0.6.12-3) ...
 => => # Selecting previously unselected package fontconfig.
 => => # Preparing to unpack .../030-fontconfig_2.13.1-2_arm64.deb ...
 => => # Unpacking fontconfig (2.13.1-2) ...
 => => # Selecting previousl
```


### General Learnings Dealing with Setups (Docker)
1. **Architecture compatibility:**
Your local machine uses an ARM-based architecture (Apple M1 chip), whereas most applications and Docker images are built for x86_64 architectures. This can lead to compatibility issues, such as executable files not running correctly.

2. **Cross-compilation and emulation:**
Docker provides a solution for running images of a different architecture via QEMU and the buildx plugin. This allows you to build and run x86_64 Docker images on an ARM machine.

3. **AWS Lambda restrictions:**
AWS Lambda has certain limitations, such as only supporting specific base images. AWS recently introduced support for container images, but there are still some restrictions to keep in mind.

4. **Chromedriver and Google Chrome compatibility:**
You need to ensure that the versions of Chromedriver and Google Chrome installed in the Docker image are compatible. Also, remember that you need to install x86_64 versions of these applications due to the architecture issues mentioned above.

5. **Installing Google Chrome:**
Depending on the base image, different methods may be needed to install Google Chrome. For instance, Ubuntu-based images can use the APT package manager, while Amazon Linux requires a different approach.

6. **Choosing the right base image:**
For AWS Lambda, you need to choose a base image that is compatible with the AWS Lambda runtime environment. For more permissive environments like Amazon Fargate, you can choose a wider range of base images.

7. **Always test your Dockerfile:**
After making changes to your Dockerfile, you should always build and test the Docker image to make sure everything works as expected. Make use of commands such as `chromedriver --version` and `chromium --version` in your Dockerfile to ensure that the required applications are installed correctly.
