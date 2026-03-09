#!/bin/sh
#
# Gradle wrapper script for Unix
#

APP_NAME="Gradle"
APP_BASE_NAME=`basename "$0"`

CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar

DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'

set -e

DIRNAME="$(dirname "$0")"
cd "$DIRNAME"

exec java $DEFAULT_JVM_OPTS -classpath $CLASSPATH org.gradle.wrapper.GradleWrapperMain "$@"
