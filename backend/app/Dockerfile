# Hacked https://aws.amazon.com/blogs/aws/new-for-aws-lambda-container-image-support/
# TODO(P0, devops): Separate this into two Lambdas, as this tries to do too many things leading to many dependency constraints.
# TODO(P1, devx): Move this to the app/ folder, restructure this project per lambda function / server.

# Define global args
ARG FUNCTION_DIR="/home/dumpsheet"
ARG RUNTIME_VERSION="3.9"
ARG DISTRO_VERSION="3.12"

# MULTISTAGE 1 - bundle base image + runtime
# Grab a fresh copy of the image and install GCC
FROM python:${RUNTIME_VERSION}-alpine${DISTRO_VERSION} AS python-alpine
# Install GCC (Alpine uses musl but we compile and link dependencies with GCC)
RUN apk add --no-cache \
    libstdc++ \
    ffmpeg

# MULTISTAGE 2 - build function and dependencies
FROM python-alpine AS build-image
# Install aws-lambda-cpp build dependencies
# postgresql-dev a libffi-dev are for psycopg[binary,pool] (this is always such a pain to install)
# git for git-based requirements (my own projects)
RUN apk add --no-cache \
    build-base \
    libtool \
    autoconf \
    automake \
    libexecinfo-dev \
    make \
    cmake \
    libcurl \
    ffmpeg \
    git \
    postgresql-dev \
    libffi-dev


ENV PYTHONUNBUFFERED=1

# Include global args in this stage of the build
ARG FUNCTION_DIR
ARG RUNTIME_VERSION
# Create function directory
RUN mkdir -p ${FUNCTION_DIR}
# We just copy the project, instead of pip install it
# NOTE: We have a .dockerignore to omit a good amount of stuff
# They say it's more standard to just copy over everything
COPY .. ${FUNCTION_DIR}/

RUN python${RUNTIME_VERSION} -m pip install --upgrade pip
# This is a bit slow.
# NOTE: To leverage Docker's layer caching,
#   make sure to put instructions that change frequently towards the end of your Dockerfile
# NOTE: Pip doesn't install packages in parallel by default.
#   However, you can use a tool like pip-accel to speed up installation by parallelizing the process.
# NOTE: Try to speed up Python requirements build time by using pre-compiled stuff from AWS Layers
RUN python${RUNTIME_VERSION} -m pip install -r ${FUNCTION_DIR}/requirements/common.txt --target ${FUNCTION_DIR}

# Install Lambda Runtime Interface Client for Python
# NOTE: This is usually provided for AWS-based images like public.ecr.aws/lambda/python:3.9
# TODO(P1, devx): Figure out how to cache this OR we can split into two lambdas. We do FROM python-alpine later hmm.
RUN python${RUNTIME_VERSION} -m pip install awslambdaric --target ${FUNCTION_DIR}

# MULTISTAGE 3 - final runtime image
# Grab a fresh copy of the Python image
FROM python-alpine
# Install libpq (PostgreSQL client library)
RUN apk add --no-cache libpq
# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}
# Copy in the built dependencies
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}
# (Optional) Add Lambda Runtime Interface Emulator and use a script in the ENTRYPOINT for simpler local runs
ADD https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie /usr/bin/aws-lambda-rie
COPY app/entry.sh /
RUN chmod 755 /usr/bin/aws-lambda-rie /entry.sh
RUN ffmpeg -version
ENTRYPOINT [ "/entry.sh" ]
CMD [ "app.app.lambda_handler" ]
