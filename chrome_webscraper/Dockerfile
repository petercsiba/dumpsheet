ARG RUNTIME_VERSION="3.9"
ARG DISTRO_VERSION="3.12"

# Stage 1 - bundle base image + runtime
# Grab a fresh copy of the image and install GCC
FROM python:${RUNTIME_VERSION}-alpine${DISTRO_VERSION} AS python-alpine

# update apk repo
# RUN echo "http://dl-4.alpinelinux.org/alpine/v${DISTRO_VERSION}/main" >> /etc/apk/repositories && \
#    echo "http://dl-4.alpinelinux.org/alpine/v${DISTRO_VERSION}/community" >> /etc/apk/repositories


# Ah, I see. The base image requirement for AWS Lambda does complicate things a bit.
# Given that you are running on Alpine, and the issue is that libnspr4.so is trying to use a function, gettid,
# that is not provided by Alpine's musl libc, there is a workaround.
# It involves using libpthread stubs for gettid from the Alpine edge testing repository.
# Add edge/testing to repositories for libpthread-stubs
RUN echo "@edge http://nl.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
# RUN echo "@testing http://nl.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories

# For UNTRUSTED signature of edge/main: --allow-untrusted
RUN apk update --allow-untrusted

# Install Chrome and ChromeDriver
RUN apk add --no-cache --allow-untrusted \
  unzip \
  chromium \
  chromium-chromedriver && \
  rm -rf /var/cache/apk/* && \
  chromium-browser --version >> /chrome_version \
  && chromedriver --version >> /chromedriver_version
# Separate RUN just for better Docker caching
RUN apk add --no-cache libpthread-stubs@edge

# Test ChromeDriver
RUN chromedriver --version

# upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

CMD [ "python", "./scraper.py" ]
