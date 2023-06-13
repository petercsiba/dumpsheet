# Hacked https://aws.amazon.com/blogs/aws/new-for-aws-lambda-container-image-support/
# docker build -t hello-world .
# docker run -p 9000:8080 hello-world
# curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'

# Docker 23 has default DOCKER_BUILDKIT=1, which should be faster.

# Pushing
# https://us-west-2.console.aws.amazon.com/ecr/repositories?region=us-west-2
# aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 680516425449.dkr.ecr.us-west-2.amazonaws.com
# docker build -t 680516425449.dkr.ecr.us-west-2.amazonaws.com/networking-summary-lambda:latest .
# docker push 680516425449.dkr.ecr.us-west-2.amazonaws.com/networking-summary-lambda:latest

# Oncall
# * Usage https://platform.openai.com/account/usage

# Define global args
ARG FUNCTION_DIR="/home/app/"
ARG RUNTIME_VERSION="3.9"
ARG DISTRO_VERSION="3.12"

# Stage 1 - bundle base image + runtime
# Grab a fresh copy of the image and install GCC
FROM python:${RUNTIME_VERSION}-alpine${DISTRO_VERSION} AS python-alpine
# Install GCC (Alpine uses musl but we compile and link dependencies with GCC)
RUN apk add --no-cache \
    libstdc++ \
    ffmpeg

# Stage 2 - build function and dependencies
FROM python-alpine AS build-image
# Install aws-lambda-cpp build dependencies
RUN apk add --no-cache \
    build-base \
    libtool \
    autoconf \
    automake \
    libexecinfo-dev \
    make \
    cmake \
    libcurl \
    ffmpeg

# Include global args in this stage of the build
ARG FUNCTION_DIR
ARG RUNTIME_VERSION
# Create function directory
RUN mkdir -p ${FUNCTION_DIR}
# Copy handler function
COPY app/* ${FUNCTION_DIR}
# Copy assets to the same dir
COPY assets/* ${FUNCTION_DIR}
# NOTE: To leverage Docker's layer caching,
#   make sure to put instructions that change frequently towards the end of your Dockerfile
# NOTE: Pip doesn't install packages in parallel by default.
#   However, you can use a tool like pip-accel to speed up installation by parallelizing the process.
# NOTE: Try to speed up Python requirements build time by using pre-compiled stuff
RUN python${RUNTIME_VERSION} -m pip install -r ${FUNCTION_DIR}/requirements.txt --target ${FUNCTION_DIR}
# Install Lambda Runtime Interface Client for Python
# TODO(P1, devx): Figure out how to cache this OR we can split into two lambdas where the other is Python-only.
RUN python${RUNTIME_VERSION} -m pip install awslambdaric --target ${FUNCTION_DIR}

# Stage 3 - final runtime image
# Grab a fresh copy of the Python image
FROM python-alpine
# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}
# Copy in the built dependencies
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}
# (Optional) Add Lambda Runtime Interface Emulator and use a script in the ENTRYPOINT for simpler local runs
ADD https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie /usr/bin/aws-lambda-rie
COPY entry.sh /
RUN chmod 755 /usr/bin/aws-lambda-rie /entry.sh
RUN ffmpeg -version
ENTRYPOINT [ "/entry.sh" ]
CMD [ "app.lambda_handler" ]
