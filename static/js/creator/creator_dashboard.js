// Creator Dashboard JavaScript - Handles client-side interactions
// including date/time display, welcome popup, and ApexCharts rendering.

/**
 * Retrieves a cookie value by its name.
 * @param {string} name - The name of the cookie to retrieve.
 * @returns {string|null} - The cookie value or null if not found.
 */
function getCookie(name) {
  let cookieValue = null
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";")
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
        break
      }
    }
  }
  return cookieValue
}

document.addEventListener("DOMContentLoaded", () => {
  // === Current Date and Time Display ===
  const dateTimeElement = document.getElementById("current-date-time-long")
  if (dateTimeElement) {
    function updateDateTime() {
      dateTimeElement.textContent = new Date().toLocaleString("en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    }
    updateDateTime() // Initial call
    setInterval(updateDateTime, 60000) // Update every minute
  }

  // === Welcome Popup Logic ===
  const showWelcomePopupDataElement = document.getElementById("show-welcome-popup-data")
  if (showWelcomePopupDataElement) {
    try {
      const showWelcomePopup = JSON.parse(showWelcomePopupDataElement.textContent)
      const welcomePopupConfigElement = document.getElementById("welcome-popup-config")
      const welcomePopupUrl = welcomePopupConfigElement ? welcomePopupConfigElement.dataset.url : null
      const csrfToken = getCookie("csrftoken")

      if (showWelcomePopup && welcomePopupUrl && csrfToken) {
        if (typeof Swal !== "undefined") {
          Swal.fire({
            title: "Welcome to Your Creator Dashboard!",
            html: `
                            <div class="text-left text-sm text-gray-600 space-y-3 p-2">
                                <p>🎉 Congratulations on becoming an approved creator!</p>
                                <p>Here's what you can do:</p>
                                <ul class="list-disc list-inside space-y-1 pl-4 marker:text-[#091e65]">
                                    <li>📚 Upload and manage your audiobooks</li>
                                    <li>📊 View detailed analytics on listens and earnings</li>
                                    <li>💳 Set up your withdrawal accounts</li>
                                    <li>💰 Request payouts for your available balance</li>
                                </ul>
                                <p class="mt-4">Explore the navigation menu to get started!</p>
                            </div>
                        `,
            icon: "success",
            iconColor: "#091e65",
            confirmButtonText: "Got it!",
            confirmButtonColor: "#091e65",
            customClass: {
              popup: "rounded-xl shadow-2xl border border-gray-200/80 font-sans",
              title: "text-2xl font-semibold text-gray-800",
              htmlContainer: "text-sm",
              confirmButton:
                "px-6 py-2.5 bg-[#091e65] text-white rounded-lg hover:bg-[#071852] focus:outline-none focus:ring-2 focus:ring-[#091e65]/50 focus:ring-offset-2 transition-all duration-200 ease-in-out shadow-md hover:shadow-lg transform hover:-translate-y-0.5",
            },
            allowOutsideClick: false,
            allowEscapeKey: false,
          }).then((result) => {
            if (result.isConfirmed) {
              fetch(welcomePopupUrl, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({}),
              })
                .then((response) => {
                  if (!response.ok) {
                    console.warn("Failed to mark welcome popup as shown on the server.")
                  }
                })
                .catch((error) => {
                  console.error("Error marking welcome popup as shown:", error)
                })
            }
          })
        } else {
          console.warn("SweetAlert2 library (Swal) is not loaded. Welcome popup cannot be displayed.")
        }
      }
    } catch (e) {
      console.error("Error processing welcome popup data:", e)
    }
  }

  // === ApexCharts Configuration ===
  if (typeof ApexCharts === "undefined") {
    const chartsToAlert = ["earningsChartContainer", "uploadsChartContainer"]
    chartsToAlert.forEach((containerId) => {
      const el = document.getElementById(containerId)
      if (el) {
        el.innerHTML = `<div class="flex items-center justify-center h-full"><p class="text-center text-gray-400 p-10 text-sm">📊 Chart library (ApexCharts) is not loaded. Charts cannot be displayed.</p></div>`
      }
    })
    return
  }

  // Chart Theme Configuration
  const THEME_COLORS = {
    primary: "#091e65", // AudioX Navy Blue
    secondary: "#ef4444", // Red
    gridBorder: "rgba(229, 231, 235, 0.6)",
    labelColor: "#6b7280",
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
  }

  /**
   * Renders an ApexChart with consistent theming
   * @param {string} chartDivId - The ID of the div where the chart will be rendered
   * @param {string} chartDataElId - The ID of the script tag containing the chart data (JSON)
   * @param {string} chartName - A descriptive name for the chart (for error messages)
   * @param {string} seriesName - The name of the data series
   * @param {function} yAxisFormatter - A function to format Y-axis labels
   * @param {string} chartType - Type of chart ('area' or 'bar')
   * @param {boolean} dataIsCounts - True if Y-axis data represents counts
   * @param {string} specificColor - The primary color for the chart series
   */
  function renderChart(
    chartDivId,
    chartDataElId,
    chartName,
    seriesName,
    yAxisFormatter,
    chartType = "area",
    dataIsCounts = false,
    specificColor = THEME_COLORS.primary,
  ) {
    const chartDataEl = document.getElementById(chartDataElId)
    const chartDiv = document.getElementById(chartDivId)

    if (!chartDataEl || !chartDiv) {
      if (chartDiv) {
        chartDiv.innerHTML = `<div class="flex items-center justify-center h-full"><p class="text-center text-gray-400 p-10 text-sm">❌ Chart cannot be displayed (missing HTML elements for ${chartName.toLowerCase()}).</p></div>`
      }
      console.error(`Chart rendering failed for ${chartName}: Missing chartDiv or chartDataEl.`)
      return
    }

    let chartRawData
    const rawTextContent = chartDataEl.textContent

    try {
      chartRawData = JSON.parse(rawTextContent)
      // Handle double-stringified data from Django template
      if (typeof chartRawData === "string") {
        chartRawData = JSON.parse(chartRawData)
      }
    } catch (e) {
      chartDiv.innerHTML = `<div class="flex items-center justify-center h-full"><p class="text-center text-red-500 p-10 text-sm">⚠️ Error loading data for ${chartName.toLowerCase()}. Please check data format.</p></div>`
      console.error(`Error parsing chart data for ${chartName}:`, e, "Raw content:", rawTextContent)
      return
    }

    // Validate chart data structure
    let dataIsValid = true
    if (!chartRawData || typeof chartRawData !== "object") {
      dataIsValid = false
    } else {
      if (!chartRawData.hasOwnProperty("labels") || !Array.isArray(chartRawData.labels)) dataIsValid = false
      if (!chartRawData.hasOwnProperty("data") || !Array.isArray(chartRawData.data)) dataIsValid = false
      if (dataIsValid && chartRawData.labels.length !== chartRawData.data.length) dataIsValid = false
    }

    if (!dataIsValid || (chartRawData && chartRawData.labels && chartRawData.labels.length === 0)) {
      chartDiv.innerHTML = `<div class="flex items-center justify-center h-full"><p class="text-center text-gray-500 p-10 text-sm">📈 No data available to display for ${chartName.toLowerCase()}.</p></div>`
      return
    }

    const options = {
      series: [
        {
          name: seriesName,
          data: chartRawData.data.map((d) => Number.parseFloat(d)),
        },
      ],
      chart: {
        type: chartType,
        height: "100%",
        toolbar: { show: false },
        zoom: { enabled: false },
        fontFamily: THEME_COLORS.fontFamily,
        parentHeightOffset: 0,
        animations: {
          enabled: true,
          easing: "easeinout",
          speed: 800,
          animateGradually: { enabled: true, delay: 150 },
        },
        foreColor: THEME_COLORS.labelColor,
      },
      colors: [specificColor],
      dataLabels: { enabled: false },
      stroke: {
        curve: "smooth",
        width: chartType === "area" ? 3 : chartType === "bar" ? 0 : 2,
      },
      fill: {
        type: "gradient",
        gradient: {
          shade: "dark",
          type: "vertical",
          shadeIntensity: chartType === "area" ? 0.4 : 0.6,
          gradientToColors: [specificColor],
          inverseColors: false,
          opacityFrom: chartType === "area" ? 0.65 : 0.9,
          opacityTo: chartType === "area" ? 0.15 : 0.75,
          stops: [0, 95, 100],
        },
      },
      xaxis: {
        categories: chartRawData.labels,
        labels: {
          style: {
            colors: THEME_COLORS.labelColor,
            fontSize: "10px",
            fontWeight: 500,
            fontFamily: THEME_COLORS.fontFamily,
          },
          rotate: -30,
          rotateAlways: false,
          hideOverlappingLabels: true,
          trim: true,
          offsetY: 2,
        },
        axisBorder: { show: false },
        axisTicks: { show: false },
        tooltip: { enabled: false },
      },
      yaxis: {
        labels: {
          style: {
            colors: THEME_COLORS.labelColor,
            fontSize: "10px",
            fontWeight: 500,
            fontFamily: THEME_COLORS.fontFamily,
          },
          formatter: yAxisFormatter,
          offsetX: -8,
        },
        min: 0,
        tickAmount: dataIsCounts
          ? Math.max(...chartRawData.data.map((d) => Number.parseFloat(d))) < 4
            ? Math.max(...chartRawData.data.map((d) => Number.parseFloat(d))) || 1
            : 4
          : 4,
      },
      grid: {
        borderColor: THEME_COLORS.gridBorder,
        strokeDashArray: 3,
        yaxis: { lines: { show: true } },
        xaxis: { lines: { show: false } },
        padding: { left: 0, right: 10, top: 5, bottom: 5 },
      },
      tooltip: {
        theme: "dark",
        style: { fontSize: "12px", fontFamily: THEME_COLORS.fontFamily },
        x: { show: true, format: "MMM yy" },
        y: {
          formatter: yAxisFormatter,
          title: { formatter: (seriesName) => seriesName + ": " },
        },
        marker: { show: true, fillColors: [specificColor] },
      },
      noData: {
        text: `📊 Gathering data for ${chartName.toLowerCase()}...`,
        align: "center",
        verticalAlign: "middle",
        offsetX: 0,
        offsetY: 0,
        style: {
          color: THEME_COLORS.labelColor,
          fontSize: "14px",
          fontFamily: THEME_COLORS.fontFamily,
        },
      },
    }

    // Bar chart specific configuration
    if (chartType === "bar") {
      options.plotOptions = {
        bar: {
          horizontal: false,
          columnWidth: "60%",
          borderRadius: 5,
          colors: {
            backgroundBarColors: ["#F3F4F6"],
            backgroundBarOpacity: 1,
          },
          dataLabels: { position: "top" },
        },
      }
      options.fill = { colors: [specificColor], opacity: 0.9 }
      options.stroke = { show: true, width: 0, colors: ["transparent"] }
    }

    const chart = new ApexCharts(chartDiv, options)
    chart.render()
  }

  // === Render Charts ===

  // Earnings Chart (Navy Blue)
  renderChart(
    "earningsChart",
    "earnings-chart-data",
    "Earnings Chart",
    "Earnings (Rs.)",
    (value) => "Rs. " + Number.parseFloat(value).toFixed(2),
    "area",
    false,
    THEME_COLORS.primary,
  )

  // Uploads Chart (Red)
  renderChart(
    "uploadsChart",
    "uploads-chart-data",
    "Uploads Chart",
    "Audiobooks Uploaded",
    (value) => Number.parseInt(value) + (Number.parseInt(value) === 1 ? " upload" : " uploads"),
    "bar",
    true,
    THEME_COLORS.secondary,
  )
})
