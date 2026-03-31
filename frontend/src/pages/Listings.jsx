import React, { useEffect, useState } from 'react'
import Grid from '@mui/material/Grid'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogTitle from '@mui/material/DialogTitle'
import DialogContent from '@mui/material/DialogContent'
import DialogActions from '@mui/material/DialogActions'
import TextField from '@mui/material/TextField'
import Filters from '../components/Filters'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function Listings({ filterLocation }){
  const [listings, setListings] = useState([])
  const [limit] = useState(20)
  const [locations, setLocations] = useState([])
  const [selectedLocation, setSelectedLocation] = useState(filterLocation || '')
  const [filters, setFilters] = useState({
    type: '',
    location: '',
    purpose: '',
    minPrice: '',
    maxPrice: ''
  })
  const [loading, setLoading] = useState(false)
  const [editingListing, setEditingListing] = useState(null)
  const [editForm, setEditForm] = useState({
    prop_type: '',
    purpose: '',
    covered_area: '',
    price: '',
    location: '',
    beds: '',
    baths: ''
  })

  useEffect(()=>{
    fetchLocations()
  },[])

  useEffect(()=>{
    fetchListings()
  },[limit, selectedLocation])

  useEffect(()=>{
    if(filterLocation){
      setSelectedLocation(filterLocation)
    }
  },[filterLocation])

  async function fetchListings(){
    try{
      setLoading(true)
      const url = new URL(API + '/listings')
      url.searchParams.set('limit', limit)

      // Use selected location from Locations page if set
      if(selectedLocation){
        url.searchParams.set('location', selectedLocation)
      }

      // Apply filter values to backend query
      if(filters.location){
        url.searchParams.set('location', filters.location)
      }
      if(filters.type){
        url.searchParams.set('prop_type', filters.type)
      }
      if(filters.purpose){
        url.searchParams.set('purpose', filters.purpose)
      }
      if(filters.minPrice){
        url.searchParams.set('min_price', filters.minPrice)
      }
      if(filters.maxPrice){
        url.searchParams.set('max_price', filters.maxPrice)
      }

      const resp = await fetch(url.toString())
      const data = await resp.json()
      setListings(data || [])
    }catch(err){
      console.error('fetchListings', err)
    }finally{
      setLoading(false)
    }
  }

  async function fetchLocations(){
    try{
      const resp = await fetch(API + '/locations')
      const data = await resp.json()
      setLocations(data.locations || [])
    }catch(err){
      console.error('fetchLocations', err)
    }
  }

  function handleApplyFilters(){
    fetchListings()
  }

  function formatPrice(p){
    if(p===undefined || p===null) return 'N/A'
    const num = Number(p)
    if(Number.isNaN(num)) return p
    return num.toLocaleString(undefined, { style: 'currency', currency: 'PKR', maximumFractionDigits:0 })
  }

  function openEditDialog(listing){
    setEditingListing(listing)
    setEditForm({
      prop_type: listing.prop_type || '',
      purpose: listing.purpose || '',
      covered_area: listing.covered_area ?? '',
      price: listing.price ?? '',
      location: listing.location || '',
      beds: listing.beds ?? '',
      baths: listing.baths ?? ''
    })
  }

  function closeEditDialog(){
    setEditingListing(null)
  }

  function handleEditChange(field, value){
    setEditForm((prev) => ({ ...prev, [field]: value }))
  }

  async function submitListingUpdate(){
    if(!editingListing?.id){
      return
    }

    const payload = {
      prop_type: editForm.prop_type,
      purpose: editForm.purpose,
      covered_area: editForm.covered_area === '' ? null : Number(editForm.covered_area),
      price: editForm.price === '' ? null : Number(editForm.price),
      location: editForm.location,
      beds: editForm.beds === '' ? null : Number(editForm.beds),
      baths: editForm.baths === '' ? null : Number(editForm.baths)
    }

    try{
      const resp = await fetch(`${API}/listings/${editingListing.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if(!resp.ok){
        const errorData = await resp.json().catch(()=>({}))
        throw new Error(errorData.detail || 'Failed to update listing')
      }
      await fetchListings()
      closeEditDialog()
    }catch(err){
      console.error('submitListingUpdate', err)
      alert(err.message || 'Could not update listing')
    }
  }

  async function handleDeleteListing(listingId){
    if(!listingId){
      return
    }
    const confirmed = window.confirm('Are you sure you want to delete this listing?')
    if(!confirmed){
      return
    }

    try{
      const resp = await fetch(`${API}/listings/${listingId}`, { method: 'DELETE' })
      if(!resp.ok){
        const errorData = await resp.json().catch(()=>({}))
        throw new Error(errorData.detail || 'Failed to delete listing')
      }
      await fetchListings()
    }catch(err){
      console.error('handleDeleteListing', err)
      alert(err.message || 'Could not delete listing')
    }
  }

  return (
    <div>
      <Filters
        filters={filters}
        setFilters={setFilters}
        onApply={handleApplyFilters}
        locations={locations}
      />
      <Grid container spacing={3}>
        {loading && listings.length === 0 && (
          <>
            {[...Array(6)].map((_, i) => (
              <Grid item xs={12} md={6} lg={4} key={`skeleton-${i}`}>
                <Card className="property-card skeleton-card" />
              </Grid>
            ))}
          </>
        )}
        {listings.map((l) => (
          <Grid item xs={12} md={6} lg={4} key={l.id}>
            <Card className="property-card" sx={{ borderRadius: 3, boxShadow: 3, overflow: 'hidden', background: 'linear-gradient(135deg, rgba(103,58,183,0.06), rgba(156,39,176,0.03))' }}>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent:'space-between', alignItems:'center', mb:1 }}>
                  <Typography variant="h6" sx={{ fontWeight:700 }}>
                    {l.prop_type}
                    <Typography component="span" sx={{ ml:1, fontSize:12, color:'gray' }}>
                      {l.purpose}
                    </Typography>
                  </Typography>
                  <Chip 
                    label={l.location} 
                    size="small" 
                    variant="outlined"
                    sx={{
                      borderColor: '#8e24aa',
                      color: '#6a1b9a',
                      fontWeight: 600,
                    }}
                  />
                </Box>
                <Typography variant="subtitle1" sx={{ color: '#6a1b9a' , fontWeight:700 }}>
                  {formatPrice(l.price)}
                </Typography>
                <Typography variant="body2" sx={{ mt:1, color:'rgba(0,0,0,0.7)' }}>
                  {l.covered_area || 'Area N/A'}
                </Typography>
                <Typography variant="body2" sx={{ mt:0.5, color:'rgba(0,0,0,0.7)'}}>
                  Beds: {l.beds || '-'} &nbsp;|&nbsp; Baths: {l.baths || '-'}
                </Typography>
                <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                  <Button variant="outlined" size="small" onClick={() => openEditDialog(l)}>
                    Update
                  </Button>
                  <Button variant="contained" color="error" size="small" onClick={() => handleDeleteListing(l.id)}>
                    Delete
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Dialog open={Boolean(editingListing)} onClose={closeEditDialog} fullWidth maxWidth="sm">
        <DialogTitle>Update Listing</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'grid', gap: 2, mt: 1 }}>
            <TextField label="Property Type" value={editForm.prop_type} onChange={(e) => handleEditChange('prop_type', e.target.value)} />
            <TextField label="Purpose" value={editForm.purpose} onChange={(e) => handleEditChange('purpose', e.target.value)} />
            <TextField label="Covered Area" type="number" value={editForm.covered_area} onChange={(e) => handleEditChange('covered_area', e.target.value)} />
            <TextField label="Price" type="number" value={editForm.price} onChange={(e) => handleEditChange('price', e.target.value)} />
            <TextField label="Location" value={editForm.location} onChange={(e) => handleEditChange('location', e.target.value)} />
            <TextField label="Beds" type="number" value={editForm.beds} onChange={(e) => handleEditChange('beds', e.target.value)} />
            <TextField label="Baths" type="number" value={editForm.baths} onChange={(e) => handleEditChange('baths', e.target.value)} />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditDialog}>Cancel</Button>
          <Button onClick={submitListingUpdate} variant="contained">Save Changes</Button>
        </DialogActions>
      </Dialog>
    </div>
  )
}
