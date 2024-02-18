import './history.css'
import './App.css'
import React, { useState } from 'react';
import { FormControl, InputLabel, Button, Container, Select, MenuItem } from '@mui/material';

function retrieveOldSamples() {
    return 'hi'
}

function History() {
    const [title, setTitle] = useState('hello')
    const listRuns = ['Lu9INpgb6O']
    // fetch all the URL's related to the run 
    const titles = ['hello', 'hi', 'other', 'stugg']
    // fetch the title for each runId from the endpoint 

    const handleChange = (event) => {
        setTitle(event.target.value);
    };

    return (
        <div className="App">
            <header className="App-header">
                <h1 className="logo">Smplr</h1>
                <Container maxWidth="sm" style={{ margin: '20px' }}>
                <FormControl fullWidth style={{ marginBottom: '20px' }}>
                        <InputLabel id="url-select-label">History</InputLabel>
                        <Select
                            labelId="url-select-label"
                            id="demo-simple-select"
                            value={title}
                            label="Title"
                            onChange={handleChange}
                        >
                            {titles.map((title, index) => (
                                <MenuItem key={index} value={title}>{title}</MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                    <Button
                        variant="contained"
                        color="primary"
                        onClick={retrieveOldSamples}
                        size='medium'
                        style={{ 'backgroundColor': 'chocolate' }}
                    >Retrieve Samples</Button>
                </Container>
                <Container>
                    <p>{title}</p>
                </Container>
            </header>
        </div>
    );
}

export default History;