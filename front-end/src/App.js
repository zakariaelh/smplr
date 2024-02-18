import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import { Container, TextField, Button, ToggleButtonGroup, ToggleButton } from '@mui/material';
import { FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import IconButton from '@mui/material/IconButton';
import DownloadIcon from '@mui/icons-material/Download';
import LinearProgress from '@mui/material/LinearProgress';
import Box from '@mui/material/Box';
import '@fontsource/inter/300.css'; // Weight 500.

const backendURL = '';
// const backendURL = 'https://zakariaelh--vocalizer-entrypoint-dev.modal.run'
// const backendURL = 'https://zakariaelh--smplr-entrypoint.modal.run';

function retrieveOldSamples() {
  return 'hi'
}


function App() {
  const [textProgress, setTextProgress] = useState('');
  const [numProgress, setNumProgress] = useState(0);
  const [url, setUrl] = useState('');
  const [audioUrls, setAudioUrls] = useState([]);
  const [speakerResult, setSpeakerResult] = useState('');
  const [showProgressBar, setShowProgressBar] = useState(false);
  // const [intervalId, setIntervalID] = useState(null);
  const intervalIdRef = useRef(null);
  const [isProgressError, setIsProgressError] = useState(false);
  const [userPage, setUserPage] = useState('new query');

  useEffect(() => {
    // In a real app, you'd start the process here and update progress based on backend updates
  }, []);

  const handleUrlChange = (e) => {
    setUrl(e.target.value);
  };

  function resetProgressBar() {
    setIsProgressError(false);
    setNumProgress(true);
    setShowProgressBar(true)
  }

  function updateProgressBar(text, isFinal, isError) {
    // clear any fake progress 
    if (intervalIdRef.current) {
      clearInterval(intervalIdRef.current);
      intervalIdRef.current = null; // Reset the ref after clearing the interval
    }

    // remove the progress bar if that's the last
    if (isFinal) {
      setTextProgress(text)
      setShowProgressBar(false)
    } else if (isError) {
      setTextProgress(text ? text : 'Error processing URL');
      // change the color of the bar to red 
      setIsProgressError(true);
    } else {
      setNumProgress(
        prevProgress => prevProgress < 50 ? prevProgress + 5 : Math.min(Math.floor(prevProgress + (100 - prevProgress) / 5), 99));
      // start incrementing one second at a time 
      intervalIdRef.current = setInterval(() => {
        setNumProgress(prevProgress => Math.min(prevProgress + 1, 99));
      }, 5000); // Update every second
      if (text) {
        setTextProgress(text)
      }
    }
  }

  async function fetchStreamableAudios(filePaths) {
    updateProgressBar('Fetching your samples')

    // Function to fetch audio with retry logic
    async function fetchAudioWithRetry(filePath, retries = 3) {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          const retrieveSampleEndpoint = '/retrieve-sample'
          const response = await fetch(`${backendURL}${retrieveSampleEndpoint}?audio_id=${encodeURIComponent(filePath)}`);
          console.log('response fetching audio', response)
          if (!response.ok) throw new Error('Failed to fetch audio');
          const audioUrl = URL.createObjectURL(await response.blob());
          return audioUrl;
        } catch (error) {
          console.error(`Attempt ${attempt} - Error fetching audio:`, error);
          if (attempt === retries) return null;
        }
      }
    }

    const urls = await Promise.all(filePaths.map(filePath => fetchAudioWithRetry(filePath)));
    console.log('audio urls', urls);

    // Filter out any null values and update state
    // Filter out any null values
    const validUrls = urls.filter(url => url !== null);

    // Say how many speakers found and add the URLs to the page
    const plural = validUrls.length > 1
    setSpeakerResult(`${validUrls.length} speaker${plural ? 's' : ''} ha${plural ? 've' : 's'} been found`);
    setAudioUrls(validUrls);
    updateProgressBar("Done", true);
  }

  async function getVideoDetails(urlToValidate) {
    // Construct the full URL for the request, including the URL to validate as a query parameter
    console.log('validating URL', url)
    const endpoint = `${backendURL}/url-details?url=${encodeURIComponent(urlToValidate)}`;

    try {
      const response = await fetch(endpoint, {
        method: 'GET',
      });

      console.log('response while validating url', response);

      // Check if the request was successful
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const videoDetails = await response.json();
      console.log('video details response', videoDetails);

      if (videoDetails.error) {
        return null
      } else {
        return videoDetails
      }
    } catch (error) {
      console.error("Error during URL validation:", error);
      return null;
    }
  }

  // async function handleSubmit() {
  //   fetchStreamableAudios(['Silver Springs (Live)_000.mp3', 'lywLCB47f1.wav'])
  // }

  async function handleSubmit() {
    // reset progress bar 
    resetProgressBar()

    try {
      console.log('validate URL', url)
      updateProgressBar('Validating URL')
      let segmentLength;
      // const isValid = true
      const videoDetails = await getVideoDetails(url);
      if (!videoDetails) {
        console.log(videoDetails)
        updateProgressBar("Invalid URL", false, true);
        throw new Error('Invalid URL')
      } else {
        // handle video details like video length 
        updateProgressBar(videoDetails.title)
        // number of chunks to break the video to
        const numberChunks = Math.max(videoDetails.length < 360 ? Math.floor(videoDetails.length / 60) : 6, 1);
        // segment length 
        segmentLength = Math.ceil(videoDetails.length / numberChunks);
        console.log(`Splitting video in ${numberChunks} chunks with a segment length of ${segmentLength}`);
      }

      console.log('Processing URL:', url);

      updateProgressBar('Contacting the backend')

      // Make a POST request to start the process and get streamed responses
      const response = await fetch(`${backendURL}/sample`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: url, segment_length: segmentLength }), // Send the URL in the request body
      });

      console.log('response from sample', response);

      // Check if the response is OK
      if (!response.body || !response.ok) {
        console.log(response);
        throw new Error('Failed to start the process or get the response stream.');
      }

      // get the run_id 
      const resp_json = await response.json();
      console.log('response json from /sample', resp_json);
      const run_id = resp_json.run_id;

      // start polling progress
      const intervalId = setInterval(() => {
        fetch(`${backendURL}/progress?run_id=${run_id}`)
          .then(response => response.json())
          .then(data => {
            console.log(data); // Log the response data
            if (data.is_final) {
              // get the results 
              const audioPaths = data.results;
              clearInterval(intervalId);
              console.log('Processing finished');
              updateProgressBar(data.text, false, false);
              // get the results from the backend 
              fetchStreamableAudios(audioPaths)
            } else if (data.error) {
              clearInterval(intervalId); // Stop the interval
              console.log('Stopping due to error :', data.error);
              updateProgressBar(data.text, true, true)
            } else {
              console.log('Received progress: ', data.text);
              updateProgressBar(data.text, false, false)
            }
          })
          .catch(error => {
            console.error('Error fetching progress data:', error);
            clearInterval(intervalId); // Stop the interval on fetch error
          });
      }, 5000); // Call the endpoint every 5 seconds
    } catch (error) {
      updateProgressBar("Failed to process your URL", false, true)
      console.error('Error:', error);
    }
  };

  const progressBar = (<Container maxWidth="sm" style={{ margin: '20px' }}>
    <Box sx={{ width: '100%' }}>
      <LinearProgress variant="determinate" value={numProgress} sx={{
        // Apply red color if there is an error, else default color
        '& .MuiLinearProgress-bar': {
          backgroundColor: isProgressError ? 'red' : undefined,
        },
      }} />
      <p id="text-progress">
        {textProgress} ... (Please do not close or refresh this page)
      </p>
    </Box>
  </Container>)

  // function downloadAudioButton(audioURL) {
  //   const a = document.createElement('a')
  //   a.href = audioURL
  //   return <Button onClick={() => a.click()}>Download</Button>
  // }

  function SelectHistoryURLs() {
    const [title, setTitle] = useState('hello')
    const listRuns = ['Lu9INpgb6O']
    // fetch all the URL's related to the run 
    const titles = ['hello', 'hi', 'other', 'stugg']
    // fetch the title for each runId from the endpoint 

    const handleURLSelection = (event) => {
      setTitle(event.target.value);
    };

    return (
      <div className='user-input'>
      <Container maxWidth="sm" >
        <FormControl fullWidth>
          <InputLabel id="url-select-label">History</InputLabel>
          <Select
            labelId="url-select-label"
            id="demo-simple-select"
            value={title}
            label="Title"
            onChange={handleURLSelection}
          >
            {titles.map((title, index) => (
              <MenuItem key={index} value={title}>{title}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </ Container>
      </div>
    )
  }

  function urlInput() {
    return (
    <div className='user-input'>
    <Container maxWidth="sm">
      <TextField
        fullWidth
        label="Enter YouTube URL"
        variant="outlined"
        value={url}
        onChange={handleUrlChange}
        margin='normal'
        style={{
          'backgroundColor': 'white',
          'borderRadius': '5px',
          'margin': '0px'
        }}
        InputProps={{
          autoComplete: 'off', // Disable autofill/autocomplete
        }}
      />
    </Container>
    </div>
    )
  }

  function samplesResult() {
    return (<Container>
      <p>
        {speakerResult}
      </p>
      <div id="audios">
        {audioUrls.map((audioUrl, index) => (
          <div className="single-audio-container">
            <audio style={{ margin: '20px' }} key={index} controls src={audioUrl}>
              Your browser does not support the audio element.
            </audio>
            {downloadAudioButton(index, audioUrl)}
          </div>
        ))}
      </div>
    </Container>)
  }

  function pageSelectionToggle() {
    const handlePageSelection = (event, a) => {
      console.log(event, a)
      if (a !== null) {
        setUserPage(a);
      }
    };

    return (
      <ToggleButtonGroup
        color='primary'
        value={userPage}
        exclusive
        onChange={handlePageSelection}
        aria-label="user-page"
      >
        <ToggleButton value="new query" aria-label="new-query" style={{
          borderRadius: '20px 0px 0px 20px',
          borderRight: '0px'
        }}>
          New Query
        </ToggleButton>
        <ToggleButton value="history" aria-label="history" style={{
          borderRadius: '0px 20px 20px 0px',
          borderLeft: '0px'
        }} disabled>
          History (coming)
        </ToggleButton>
      </ToggleButtonGroup>
    );
  }

  function downloadAudioButton(index, audioURL) {
    return <a className="download-container" href={audioURL} download={`Sample_${index + 1}.mp3`}>
      <IconButton color="primary" aria-label="download" component="span" style={{ color: 'white' }}>
        <DownloadIcon />
      </IconButton>
    </a>
  }


  return (
    <div className="App">
      <header className="App-header">
        <h1 className="logo">Smplr</h1>
        <div>
          {pageSelectionToggle()}
        </div>
        <div style={{ display: userPage === 'new query' ? 'block' : 'none' }}>
          {urlInput()}
        </div>
        <div style={{ display: userPage === 'history' ? 'block' : 'none' }}>
          {SelectHistoryURLs()}
        </div>
        {showProgressBar ? progressBar : null}
        <Container>
          <Button
            variant="contained"
            color="primary"
            onClick={handleSubmit}
            size='medium'
            style={{ 'backgroundColor': 'chocolate' }}
          >Process Video</Button>
        </Container>
        {samplesResult()}
      </header>
    </div>
  );
}

export default App;
