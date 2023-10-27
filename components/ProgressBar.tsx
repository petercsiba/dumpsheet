import React from 'react';

type ProgressBarProps = {
    currentStep: number;
};

const ProgressBar: React.FC<ProgressBarProps> = ({ currentStep }) => {
    return (
        <div className="w-full flex flex-col items-center mt-8">
            <div className="h-0.5 bg-gray-300 mb-4" style={{ width: '92%' }}></div> {/* Horizontal line */}
            <div className="w-full flex justify-between items-center">
                <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${currentStep === 1 ? 'bg-orange-500' : currentStep > 1 ? 'bg-green-500' : 'bg-gray-300'}`}>
                        1
                    </div>
                    <span className="text-xs mt-1 m-1 text-center">Record a Voice Memo</span>
                </div>
                <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${currentStep === 2 ? 'bg-orange-500' : currentStep > 2 ? 'bg-green-500' : 'bg-gray-300'}`}>
                        2
                    </div>
                    <span className="text-xs mt-1 mx-1 text-center">Enter Your Email</span>
                </div>
                <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${currentStep === 3 ? 'bg-orange-500' : currentStep > 3 ? 'bg-green-500' : 'bg-gray-300'}`}>
                        3
                    </div>
                    <span className="text-xs mt-1 mx-1 text-center">Receive Organized Recap</span>
                </div>
                <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${currentStep === 4 ? 'bg-orange-500' : currentStep > 4 ? 'bg-green-500' : 'bg-gray-300'}`}>
                        4
                    </div>
                    <span className="text-xs mt-1 mx-1 text-center">Review & Follow Up</span>
                </div>
            </div>
        </div>
    );
};

export default ProgressBar;