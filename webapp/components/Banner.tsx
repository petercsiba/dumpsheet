type BannerProps = {};

const Banner: React.FC<BannerProps> = ({ }) => {
    return (
        <div className="w-[16rem] absolute top-20 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black rounded-lg bg-white px-6 py-1">
            <div className="block text-black font-semibold text-center">
                We are in Private Beta
            </div>
            <div className="block text-center">
                Your feedback counts
            </div>
        </div>
    );
};

export default Banner;
