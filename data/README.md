# Data directory

The Brazilian Malware Dataset (Ceschin et al., 2018) lives here after running
the download script. Raw data is gitignored — never committed.

## Acquisition

```bash
python scripts/download_data.py
```

This clones https://github.com/fabriciojoc/brazilian-malware-dataset into
`data/brazilian-malware-dataset/`.

## Structure (after download)

```
data/
└── brazilian-malware-dataset/
    └── goodware-malware/
        ├── goodware.csv
        └── malware-by-day/
            ├── 2013-01-01.csv
            ├── 2013-01-02.csv
            └── ...   (~1,800 daily files spanning multiple years)
```

## Citation

> F. Ceschin, F. Pinage, M. Castilho, D. Menotti, L. S. Oliveira, A. Gregio.
> "The Need for Speed: An Analysis of Brazilian Malware Classifiers."
> IEEE Security & Privacy 16(6), 31-41, Nov.-Dec. 2018.
> DOI: 10.1109/MSEC.2018.2875369

## Why this dataset

The dataset is purpose-built for the temporal evaluation methodology we adopt
(Pendlebury et al., TESSERACT, USENIX Security 2019). Per-day organization
makes strict pre-T / post-T splits trivial.
