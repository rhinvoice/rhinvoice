# Validators for the e-invoices of `make einvoice-qa`:
# - KoSIT validator with the XRechnung configuration (EN 16931 and XRechnung, CII)
# - Mustang (ZUGFeRD / Factur-X PDFs: PDF/A-3 through veraPDF, XMP and the XML)
FROM eclipse-temurin:21-jre

ARG KOSIT_VERSION=1.6.3
ARG KOSIT_SHA256=799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9
ARG XRECHNUNG_RELEASE=2026-08-31
ARG XRECHNUNG_CONFIGURATION=xrechnung-3.0.2-validator-configuration-2026-08-31
ARG XRECHNUNG_SHA256=2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8
ARG MUSTANG_VERSION=2.26.0
ARG MUSTANG_SHA256=42d7868cb68264874a7b8cab4c3587b03b23ccc7cd72373da917f66758bb9736

RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/einvoice
RUN curl -fsSL -o kosit.jar \
        "https://github.com/itplr-kosit/validator/releases/download/v${KOSIT_VERSION}/validator-${KOSIT_VERSION}-standalone.jar" \
    && echo "${KOSIT_SHA256}  kosit.jar" | sha256sum -c - \
    && curl -fsSL -o xrechnung.zip \
        "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/v${XRECHNUNG_RELEASE}/${XRECHNUNG_CONFIGURATION}.zip" \
    && echo "${XRECHNUNG_SHA256}  xrechnung.zip" | sha256sum -c - \
    && unzip -q xrechnung.zip -d xrechnung \
    && rm xrechnung.zip \
    && curl -fsSL -o mustang.jar \
        "https://github.com/ZUGFeRD/mustangproject/releases/download/core-${MUSTANG_VERSION}/Mustang-CLI-${MUSTANG_VERSION}.jar" \
    && echo "${MUSTANG_SHA256}  mustang.jar" | sha256sum -c -

COPY validate.sh /opt/einvoice/validate.sh
ENTRYPOINT ["/opt/einvoice/validate.sh"]
