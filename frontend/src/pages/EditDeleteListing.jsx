import React, { useState, useEffect } from 'react'
import {
  Container,
  Paper,
  TextField,
  Button,
  Typography,
  Box,
  MenuItem,
  Alert,
  CircularProgress,
  Fade,
  Slide,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function EditDeleteListing() {
  const navigate = useNavigate()
  const [pid, setPid] = useState('')
  const [formData, setFormData] = useState({
    prop_type: '',
    purpose: 'sale',
    covered_area: '',
    price: '',
    location: '',
    beds: '',
    baths: '',
    amenities: '',
  })
  const [locations, setLocations] = useState([])
  const [propertyTypes, setPropertyTypes] = useState([])
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const [fetching, setFetching] = useState(false)
  const [found, setFound] = useState(false)

  useEffect(() => {
    fetchOptions()
  }, [])

  async function fetchOptions() {
    try {
      const [locResp, typeResp] = await Promise.all([
        axios.get(`${API}/locations`),
        axios.get(`${API}/prop_type`),
      ])
      setLocations(locResp.data.locations || [])
      setPropertyTypes(typeResp.data.prop_type || [])
    } catch (err) {
      console.error('Error fetching options:', err)
    }
  }

  const handlePidChange = (e) => {
    setPid(e.target.value)
    setError('')
    setSuccess('')
    setFound(false)
    setFormData({
      prop_type: '',
      purpose: 'sale',
      covered_area: '',
      price: '',
      location: '',
      beds: '',
      baths: '',
      amenities: '',
    })
  }

  const fetchListing = async () => {
    if (!pid) return
    setFetching(true)
    setError('')
    setSuccess('')
    try {
      const response = await axios.get(`${API}/listings/${pid}`)
      if (response.data) {
        setFormData({
          prop_type: response.data.prop_type || '',
          purpose: response.data.purpose || 'sale',
          covered_area: response.data.covered_area || '',
          price: response.data.price || '',
          location: response.data.location || '',
          beds: response.data.beds || '',
          baths: response.data.baths || '',
          amenities: response.data.amenities || '',
        })
        setFound(true)
      } else {
        setError('Listing not found.')
        setFound(false)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Listing not found.')
      setFound(false)
    } finally {
      setFetching(false)
    }
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
    setError('')
    setSuccess('')
  }

  const handleUpdate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const response = await axios.put(`${API}/listings/${pid}/update`, {
        prop_type: formData.prop_type,
        purpose: formData.purpose,
        covered_area: parseFloat(formData.covered_area),
        price: parseFloat(formData.price),
        location: formData.location,
        beds: parseInt(formData.beds, 10),
        baths: parseInt(formData.baths, 10),
        amenities: formData.amenities || '',
      })
      if (response.data.success) {
        setSuccess('Listing updated successfully!')
        setTimeout(() => {
          navigate('/')
        }, 2000)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update listing. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this listing?')) return
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const response = await axios.delete(`${API}/listings/${pid}/delete`)
      if (response.data.success) {
        setSuccess('Listing deleted successfully!')
        setTimeout(() => {
          navigate('/')
        }, 2000)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete listing. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Container maxWidth="md" sx={{ mt: 4, mb: 6 }}>
      <Fade in timeout={600}>
        <Paper
          elevation={8}
          sx={{
            p: 4,
            borderRadius: 4,
            background: 'linear-gradient(135deg, rgba(255,255,255,0.95), rgba(250,250,255,0.95))',
            boxShadow: '0 8px 32px rgba(0,0,0,0.1)',
          }}
        >
          <Slide direction="down" in timeout={500}>
            <Typography
              variant="h4"
              sx={{
                mb: 3,
                fontWeight: 700,
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                textAlign: 'center',
              }}
            >
              Edit or Delete Listing
            </Typography>
          </Slide>

          {success && (
            <Fade in timeout={400}>
              <Alert severity="success" sx={{ mb: 3 }}>
                {success}
              </Alert>
            </Fade>
          )}

          {error && (
            <Fade in timeout={400}>
              <Alert severity="error" sx={{ mb: 3 }}>
                {error}
              </Alert>
            </Fade>
          )}

          <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
            <TextField
              label="Property ID (PID)"
              value={pid}
              onChange={handlePidChange}
              type="number"
              required
              sx={{ maxWidth: 200 }}
            />
            <Button
              variant="contained"
              onClick={fetchListing}
              disabled={!pid || fetching}
              sx={{
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                minWidth: 120,
              }}
            >
              {fetching ? <CircularProgress size={20} color="inherit" /> : 'Fetch Listing'}
            </Button>
          </Box>

          {found && (
            <Box component="form" onSubmit={handleUpdate} sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}>
                <TextField
                  select
                  label="Property Type"
                  name="prop_type"
                  value={formData.prop_type}
                  onChange={handleChange}
                  required
                  fullWidth
                  SelectProps={{
                    MenuProps: {
                      PaperProps: {
                        sx: {
                          maxHeight: 300,
                        },
                      },
                    },
                  }}
                >
                  {propertyTypes.map((type) => (
                    <MenuItem key={type} value={type}>
                      {type}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  select
                  label="Purpose"
                  name="purpose"
                  value={formData.purpose}
                  onChange={handleChange}
                  required
                  fullWidth
                >
                  <MenuItem value="sale">For Sale</MenuItem>
                  <MenuItem value="rent">For Rent</MenuItem>
                </TextField>

                <TextField
                  label="Location"
                  name="location"
                  select
                  value={formData.location}
                  onChange={handleChange}
                  required
                  fullWidth
                  SelectProps={{
                    MenuProps: {
                      PaperProps: {
                        sx: {
                          maxHeight: 300,
                        },
                      },
                    },
                  }}
                >
                  {locations.map((loc) => (
                    <MenuItem key={loc} value={loc}>
                      {loc}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  label="Price (PKR)"
                  name="price"
                  type="number"
                  value={formData.price}
                  onChange={handleChange}
                  required
                  fullWidth
                  inputProps={{ min: 0, step: 1000 }}
                />

                <TextField
                  label="Covered Area (sqft)"
                  name="covered_area"
                  type="number"
                  value={formData.covered_area}
                  onChange={handleChange}
                  required
                  fullWidth
                  inputProps={{ min: 0, step: 1 }}
                />

                <TextField
                  label="Bedrooms"
                  name="beds"
                  type="number"
                  value={formData.beds}
                  onChange={handleChange}
                  required
                  fullWidth
                  inputProps={{ min: 0, max: 20 }}
                />

                <TextField
                  label="Bathrooms"
                  name="baths"
                  type="number"
                  value={formData.baths}
                  onChange={handleChange}
                  required
                  fullWidth
                  inputProps={{ min: 0, max: 20 }}
                />
              </Box>

              <TextField
                label="Amenities (optional)"
                name="amenities"
                value={formData.amenities}
                onChange={handleChange}
                fullWidth
                multiline
                rows={3}
                placeholder="e.g., Swimming pool, Gym, Parking, Security..."
              />

              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 2 }}>
                <Button
                  variant="outlined"
                  onClick={() => navigate('/')}
                  sx={{
                    borderColor: '#667eea',
                    color: '#667eea',
                    '&:hover': {
                      borderColor: '#764ba2',
                      background: 'rgba(102, 126, 234, 0.08)',
                    },
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={loading}
                  sx={{
                    minWidth: 120,
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    boxShadow: '0 4px 15px rgba(102, 126, 234, 0.4)',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #764ba2 0%, #667eea 100%)',
                      boxShadow: '0 6px 20px rgba(102, 126, 234, 0.5)',
                      transform: 'translateY(-2px)',
                    },
                    '&:disabled': {
                      background: '#ccc',
                    },
                    transition: 'all 0.3s ease',
                  }}
                >
                  {loading ? <CircularProgress size={24} color="inherit" /> : 'Update Listing'}
                </Button>
                <Button
                  variant="contained"
                  color="error"
                  onClick={handleDelete}
                  disabled={loading}
                  sx={{
                    minWidth: 120,
                    background: 'linear-gradient(135deg, #ff5858 0%, #f09819 100%)',
                    boxShadow: '0 4px 15px rgba(255, 88, 88, 0.2)',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #f09819 0%, #ff5858 100%)',
                      boxShadow: '0 6px 20px rgba(255, 88, 88, 0.3)',
                      transform: 'translateY(-2px)',
                    },
                    '&:disabled': {
                      background: '#ccc',
                    },
                    transition: 'all 0.3s ease',
                  }}
                >
                  {loading ? <CircularProgress size={24} color="inherit" /> : 'Delete Listing'}
                </Button>
              </Box>
            </Box>
          )}
        </Paper>
      </Fade>
    </Container>
  )
}
