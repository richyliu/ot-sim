# OT-sim + halucinator demo

## Building halucinator

- clone from: https://github.com/richyliu/halucinator
  - dev branch
- build openplc demo with: `docker build -t halucinator_openplc -f openplc_demo.Dockerfile .`

## Building OT-sim

- clone from: https://github.com/richyliu/ot-sim
  - dev-halucinator branch
- build with: docker build -t ot-sim .

## Running

Use docker-compose: `docker-compose up` from this directory. To tear down (including volumes), run `docker-compose down -v`.

## Details

- halucinator communicates with the ot-sim halucinator plugin via IPC (unix domain sockets in `/tmp`)
