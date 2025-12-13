import React, { useState, useEffect } from 'react'
import axios from 'axios'
import Container from '@mui/material/Container'
import Grid from '@mui/material/Grid'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import CardActions from '@mui/material/CardActions'
import Typography from '@mui/material/Typography'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Button from '@mui/material/Button'
import Slider from '@mui/material/Slider'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import CircularProgress from '@mui/material/CircularProgress'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const Predictions = () => {
  const [formData, setFormData] = useState({
    beds: 3,
    bathrooms: 3,
    coveredArea: 1500,
    location: '',
    propType: '',
  })
  const [locations, setLocations] = useState([])
  const [propertyTypes, setPropertyTypes] = useState([])
  const [predictedPrice, setPredictedPrice] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    async function fetchOptions() {
      try {
        const [locResp, typeResp] = await Promise.all([
          axios.get(`${API}/locations`),
          axios.get(`${API}/prop_type`),
        ])
        setLocations(locResp.data.locations || [])
        setPropertyTypes(typeResp.data.prop_type || [])
      } catch (error) {
        console.error('Error fetching locations or property types:', error)
      }
    }
    fetchOptions()
  }, [])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleSliderChange = (name) => (_, value) => {
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      setLoading(true)
      const requestData = {
        ...formData,
        beds: parseInt(formData.beds, 10),
        bathrooms: parseInt(formData.bathrooms, 10),
        coveredArea: parseFloat(formData.coveredArea),
      }

      const response = await axios.post(`${API}/predict`, requestData)
      if (response.data.error) {
        alert('Error: ' + response.data.error)
      } else {
        setPredictedPrice(response.data.formatted_price)
      }
    } catch (error) {
      console.error('Error:', error)
      alert('Error getting prediction: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Container maxWidth="md" sx={{ mt: 4, mb: 6 }}>
      <Grid container spacing={4}>
        <Grid item xs={12} md={7}>
          <Card
            sx={{
              borderRadius: 4,
              overflow: 'hidden',
              boxShadow: 6,
              background: 'linear-gradient(135deg, rgba(123,31,162,0.09), rgba(156,39,176,0.03), #ffffff)',
              backdropFilter: 'blur(6px)',
            }}
          >
            <CardContent>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                Price prediction
              </Typography>
              <Typography variant="body2" sx={{ mb: 3, color: 'text.secondary' }}>
                Tune the sliders and fields to estimate a fair market price for your property.
              </Typography>

              <Box
                component="form"
                onSubmit={handleSubmit}
                sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
              >
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label="Beds"
                      name="beds"
                      type="number"
                      value={formData.beds}
                      onChange={handleChange}
                      size="small"
                      required
                      inputProps={{ min: 1, max: 10 }}
                      fullWidth
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label="Bathrooms"
                      name="bathrooms"
                      type="number"
                      value={formData.bathrooms}
                      onChange={handleChange}
                      size="small"
                      required
                      inputProps={{ min: 1, max: 10 }}
                      fullWidth
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 1 }}>
                      Covered area (sq ft)
                    </Typography>
                    <Slider
                      value={Number(formData.coveredArea)}
                      onChange={handleSliderChange('coveredArea')}
                      valueLabelDisplay="auto"
                      min={1}
                      max={1200}
                      step={5}
                      sx={{
                        color: '#7b1fa2',
                        '& .MuiSlider-thumb': {
                          '&:hover': {
                            boxShadow: '0 0 0 8px rgba(123, 31, 162, 0.16)',
                          },
                        },
                      }}
                    />
                  </Grid>
                </Grid>

                <TextField
                  select
                  label="Location"
                  name="location"
                  value={formData.location}
                  onChange={handleChange}
                  size="small"
                  required
                  sx={{ mt: 1 }}
                >
                  {locations.map((loc) => (
                    <MenuItem key={loc} value={loc}>
                      {loc}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  select
                  label="Property type"
                  name="propType"
                  value={formData.propType}
                  onChange={handleChange}
                  size="small"
                  required
                >
                  {propertyTypes.map((pt) => (
                    <MenuItem key={pt} value={pt}>
                      {pt}
                    </MenuItem>
                  ))}
                </TextField>

                <CardActions sx={{ justifyContent: 'space-between', mt: 1, px: 0 }}>
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                    <Chip label="ML-powered" color="secondary" size="small" />
                    <Typography variant="caption" color="text.secondary">
                      Uses your latest production model from MLflow
                    </Typography>
                  </Box>
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={loading}
                    sx={{
                      borderRadius: 999,
                      px: 3,
                      background: 'linear-gradient(90deg, #7b1fa2, #ab47bc)',
                    }}
                  >
                    {loading ? <CircularProgress size={18} sx={{ color: 'white' }} /> : 'Get prediction'}
                  </Button>
                </CardActions>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={5}>
          <Card
            sx={{
              borderRadius: 4,
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              boxShadow: 4,
              background: 'linear-gradient(145deg, #6a1b9a, #8e24aa, #ba68c8)',
              color: 'white',
            }}
          >
            <CardContent>
              <Typography variant="overline" sx={{ opacity: 0.8 }}>
                Estimated market value
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, mt: 1 }}>
                {predictedPrice || 'Fill details to get an estimate'}
              </Typography>

              <Divider sx={{ my: 2, borderColor: 'rgba(255,255,255,0.24)' }} />

              <Typography variant="body2" sx={{ opacity: 0.9, mb: 2 }}>
                This estimate is based on learned patterns from historical property data, including location, area,
                and bedroom/bathroom configuration.
              </Typography>

              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                <Chip
                  label={`${formData.beds} beds`}
                  variant="outlined"
                  sx={{ borderColor: 'rgba(255,255,255,0.6)', color: 'white' }}
                />
                <Chip
                  label={`${formData.bathrooms} baths`}
                  variant="outlined"
                  sx={{ borderColor: 'rgba(255,255,255,0.6)', color: 'white' }}
                />
                <Chip
                  label={`${formData.coveredArea} sq ft`}
                  variant="outlined"
                  sx={{ borderColor: 'rgba(255,255,255,0.6)', color: 'white' }}
                />
                {formData.location && (
                  <Chip
                    label={formData.location}
                    variant="outlined"
                    sx={{ borderColor: 'rgba(255,255,255,0.6)', color: 'white' }}
                  />
                )}
                {formData.propType && (
                  <Chip
                    label={formData.propType}
                    variant="outlined"
                    sx={{ borderColor: 'rgba(255,255,255,0.6)', color: 'white' }}
                  />
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  )
}

export default Predictions