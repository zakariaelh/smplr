# smplr
End-to-end platform to create voice cloning samples from youtube videos

This code use the vocal extraction code from @seanghay's repo [uvr](https://github.com/zakariaelh/clonee2e/tree/main)

To get started: 

1. Clone the repo 

```
git clone git@github.com:zakariaelh/smplr.git
cd smplr
```

2. Download the model weights
```
sh download.sh
```

3. Set up a [modal account](https://modal.com/) 

4. Serve remotely

```
modal serve smplr.py
```