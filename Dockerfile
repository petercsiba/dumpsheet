# Hacked https://aws.amazon.com/blogs/aws/new-for-aws-lambda-container-image-support/
# TODO(p0, devx): Move this to the app/ folder, restructure this project per lambda function / server.

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
# postgresql-dev a libffi-dev are for psycopg[binary,pool] (this is always such a pain to install)
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
    rust \
    cargo \
    postgresql-dev \
    libffi-dev

ENV PYTHONUNBUFFERED=1

# Include global args in this stage of the build
ARG FUNCTION_DIR
ARG RUNTIME_VERSION
# Create function directory
RUN mkdir -p ${FUNCTION_DIR}
# Install my python library
# NOTE: We do NOT copy everything, as that includes a ton of crap.
#   -> I feel like some angry dev will read this one day in disbelief.
COPY ./__init__.py ${FUNCTION_DIR}/backend/
COPY ./app ${FUNCTION_DIR}/backend/app
COPY ./common ${FUNCTION_DIR}/backend/common
COPY ./setup.py ${FUNCTION_DIR}/backend/
RUN python${RUNTIME_VERSION} -m pip install ${FUNCTION_DIR}/backend

RUN python${RUNTIME_VERSION} -m pip install --upgrade pip
# NOTE: To leverage Docker's layer caching,
#   make sure to put instructions that change frequently towards the end of your Dockerfile
# NOTE: Pip doesn't install packages in parallel by default.
#   However, you can use a tool like pip-accel to speed up installation by parallelizing the process.
# NOTE: Try to speed up Python requirements build time by using pre-compiled stuff
# !NOTE! We use  app/requirements.txt as we do NOT need the research deps stuff (installing pandas/numpy is heavy).
RUN python${RUNTIME_VERSION} -m pip install -r ${FUNCTION_DIR}/backend/app/requirements.txt --target ${FUNCTION_DIR}

# Install Lambda Runtime Interface Client for Python
# TODO(P1, devx): Figure out how to cache this OR we can split into two lambdas where the other is Python-only.
RUN python${RUNTIME_VERSION} -m pip install awslambdaric --target ${FUNCTION_DIR}

# Stage 3 - final runtime image
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
CMD [ "backend.app.lambda_handler" ]
