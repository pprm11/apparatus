# sealed/

Paths listed under `sealed` in `layer.json` are never committed in clear text: the sync stores age-encrypted
copies here (`age -r <public-key>`). The private key lives in a password manager, never in a repo or in
`~/.claude`. To read a copy: `age -d -i <key-file> <file>.age`.
