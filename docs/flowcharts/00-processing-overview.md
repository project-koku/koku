```mermaid

graph

A["Orchestrator.prepare()"] --> B[start-manifest-processing]
B --> C["ReportDownloader()"]
C --> D["get manifest list\n(download manifest, insert manifest record)"]
D --> |"iterate over manifests (only GCP has more than 1)"| E["ensure each file of manifest has status record (weirdly done)"]
E --> |iterate over each file of manifest| F[generate new `report_context` dict from manifest copy]
F --> G[create list of tasks to download report file]
G --> H[trigger task to download files (pass in report context and account info)]

H --> I[get_report_files]
I --> J[_get_report_files]
J --> K["ReportDownloader()"]
K --> L[download file]




```


H --> I[trigger summary tasks]
H --> J[trigger hcs tasks]
H --> K[trigger subs tasks]
