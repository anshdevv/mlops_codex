import React, { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Container from '@mui/material/Container'
import NavBar from './components/NavBar'

import Listings from './pages/Listings'
import Locations from './pages/Locations'
import AddListing from './pages/AddListing'
import EditDeleteListing from './pages/EditDeleteListing'
import CompareProperties from './pages/CompareProperties'
import ChatBotPage from './pages/ChatBotPage'


export default function App(){
  const [filterLocation, setFilterLocation] = useState(null)

  return (
    <div>
      <NavBar />
      <Container sx={{ mt: 4 }}>
        <Routes>
          <Route path="/" element={<Listings filterLocation={filterLocation} />} />
          <Route path="/locations" element={<Locations onSelectLocation={setFilterLocation} />} />
          <Route path="/add-listing" element={<AddListing />} />
          <Route path="/edit-delete-listing" element={<EditDeleteListing />} />
          <Route path="/compare" element={<CompareProperties />} />
          <Route path="/chatbot" element={<ChatBotPage />} />
        </Routes>
      </Container>
    </div>
  )
}
