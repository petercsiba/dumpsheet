
function debugError(error: unknown): void {
  if (error instanceof Error) {
    console.error('An error occurred:', error.message);
    console.error('Call stack:', error.stack);
  } else {
    // Log the error as an unknown type
    console.error('An unexpected type of error occurred:', error);
  }
}

// Mostly for INT values over 1000
export function formatFileSizeShort(value: number | null | undefined): string {
  if (value == null) {
    return 'N/A';
  }
  // Define suffixes and their thresholds
  const suffixes = [
    { threshold: 1024 * 1024 * 1024, suffix: " GB" }, // Billions
    { threshold: 1024 * 1024, suffix: " MB" }, // Millions
    { threshold: 1024, suffix: " KB" }, // Thousands
  ];

  // Helper function to remove trailing ".0" if present
  function cleanTrailingZero(numStr: string): string {
    return numStr.replace(/\.0/, '');
  }

  // Loop through the suffixes to find an appropriate threshold
  for (const { threshold, suffix } of suffixes) {
    if (value >= threshold) {
      return `${cleanTrailingZero((value / threshold).toFixed(1))}${suffix}`;
    }
  }

  // Format without suffix if below the thousands threshold
  let formattedValue: string;
  if (value < 10) {
    formattedValue = "N/A"
    try {
      // Your code that might throw an error
      formattedValue = `${value.toFixed(2)}`; // 2 decimal places for values less than 10
    } catch (error) {
      debugError(error);
      throw error;
    }
  } else if (value < 100) {
    formattedValue = `${value.toFixed(1)}`; // 1 decimal place for values between 10 and 99
  } else {
    formattedValue = `${value.toFixed(0)}`; // 0 decimal places for values 100 and above
  }

  return cleanTrailingZero(formattedValue);
}
