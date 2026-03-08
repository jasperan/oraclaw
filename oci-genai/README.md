# OCI Generative AI Integration for OracLaw

This directory provides **OCI Generative AI** as an optional LLM backend for OracLaw. It uses the [`oci-openai`](https://pypi.org/project/oci-openai/) Python library to expose OCI GenAI through an OpenAI-compatible local proxy, so OracLaw can consume it like any other OpenAI-compatible provider.

> **Note:** The default providers (Anthropic, OpenAI, Ollama) remain unchanged. OCI GenAI is an additional, optional backend.

## Prerequisites

- **Python 3.11+**
- **OCI CLI config** (`~/.oci/config`) with a valid profile — see [OCI SDK Configuration](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
- **OCI compartment** with Generative AI service enabled

## Quick Start

1. **Install dependencies:**

   ```bash
   cd oci-genai
   pip install -r requirements.txt
   ```

2. **Set environment variables:**

   ```bash
   export OCI_PROFILE=DEFAULT                    # OCI config profile name
   export OCI_REGION=us-chicago-1                 # OCI region
   export OCI_COMPARTMENT_ID=ocid1.compartment.oc1..your-compartment-ocid
   ```

3. **Start the proxy:**

   ```bash
   python proxy.py
   # Proxy runs at http://localhost:9999/v1
   ```

4. **Configure OracLaw** to use the proxy as a custom OpenAI-compatible provider:

   | Setting    | Value                                           |
   | ---------- | ----------------------------------------------- |
   | `base_url` | `http://localhost:9999/v1`                      |
   | `api_key`  | `oci-genai` (any value; auth is handled by OCI) |
   | `model`    | `meta.llama-3.3-70b-instruct`                   |

## Environment Variables

| Variable             | Default        | Description                                  |
| -------------------- | -------------- | -------------------------------------------- |
| `OCI_PROFILE`        | `DEFAULT`      | OCI config profile name from `~/.oci/config` |
| `OCI_REGION`         | `us-chicago-1` | OCI region for the GenAI endpoint            |
| `OCI_COMPARTMENT_ID` | _(required)_   | OCI compartment OCID                         |
| `OCI_PROXY_PORT`     | `9999`         | Local proxy listen port                      |

## Available OCI GenAI Models

OCI Generative AI provides access to several model families:

- **Meta Llama** -- `meta.llama-3.3-70b-instruct`, `meta.llama-3.1-405b-instruct`
- **Cohere** -- `cohere.command-r-plus`, `cohere.command-r`
- **xAI Grok** -- available in select regions

Model availability varies by region. Check the [OCI GenAI documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm) for the latest list.

## Architecture

```
OracLaw  -->  oci-genai/proxy.py (localhost:9999)  -->  OCI GenAI Service
               (OpenAI-compatible)                      (OCI User Principal Auth)
```

The proxy translates standard OpenAI API calls (`/v1/chat/completions`) into authenticated requests to OCI GenAI using your `~/.oci/config` credentials. No separate API keys are needed.

## Files

| File               | Description                             |
| ------------------ | --------------------------------------- |
| `oci_client.py`    | OCI GenAI client wrapper (sync + async) |
| `proxy.py`         | Local OpenAI-compatible proxy server    |
| `requirements.txt` | Python dependencies                     |

## Documentation

- [OCI Generative AI Service](https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm)
- [oci-openai on PyPI](https://pypi.org/project/oci-openai/)
- [OCI SDK Configuration](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
