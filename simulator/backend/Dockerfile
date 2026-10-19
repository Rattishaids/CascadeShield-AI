FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /source
ARG MAVEN_MIRROR_URL=""
COPY pom.xml mirror-settings.xml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 if [ -n "$MAVEN_MIRROR_URL" ]; then mvn -s mirror-settings.xml -B -q package; else mvn -B -q package; fi
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /source/target/simulator-0.1.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java","-XX:MaxRAMPercentage=65","-jar","app.jar"]
