#!/bin/sh
# Run from simulator/backend inside the existing Maven image and mounted Maven cache.
set -eu
exec java -Xmx"${ML_JAVA_HEAP:-1024m}" -cp "$(cat target/ml-classpath.txt)" "$@"
